import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import pyotp
import os
from sheets_auth_selector import load_clients_from_sheets
from events_extractor import format_event_to_df, save_all_to_sqlite, log_failed_client
import config

# 드라이버 초기화

def init_driver():
    """
    리눅스 환경에서 안정적으로 동작하도록 ChromeOptions를 설정합니다.
    """
    try:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_experimental_option("excludeSwitches", ['enable-logging'])
        chrome_options.add_argument("headless")
        chrome_options.add_argument("window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(
            service=Service(config.CHROMEDRIVER_PATH),
            options=chrome_options
        )
        driver.implicitly_wait(config.IMPLICIT_WAIT)
    except Exception as e:
        print('에러 발생: ', e)
        return None
    return driver


def get_count_and_events(client, driver, section_name, count_xpath, button_xpath, tbody_xpath, detail_xpath):
    try:
        link = WebDriverWait(driver, config.EXPLICIT_WAIT).until(
            EC.visibility_of_element_located((By.XPATH, count_xpath))
        )
        count_text = link.text.strip()
        count = int(re.search(r'\d+', count_text).group() if re.search(r'\d+', count_text) else '0')
    except TimeoutException:
        count = 0

    events = []
    if count > 0:
        try:
            button = WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                EC.element_to_be_clickable((By.XPATH, button_xpath))
            )
            button.click()
            time.sleep(config.SLEEP_SHORT)

            WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                EC.presence_of_element_located((By.XPATH, tbody_xpath))
            )
            rows = driver.find_elements(By.XPATH, f"{tbody_xpath}/tr")
            if not rows:
                return count, events

            for row in rows:
                try:
                    # 이벤트 링크 및 제목 추출
                    event_link_elem = row.find_element(By.XPATH, "./td[2]/div/a")
                    event_title = event_link_elem.text.strip()
                    if not event_title:
                        continue

                    # 상세 클릭 전 방해 요소 숨김
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", event_link_elem)
                    driver.execute_script("window.scrollBy(0, -100);")
                    try:
                        span = driver.find_element(By.CSS_SELECTOR, config.INTERFERING_SPAN_SELECTOR)
                        driver.execute_script("arguments[0].style.display='none';", span)
                    except Exception:
                        pass

                    driver.execute_script("arguments[0].click();", event_link_elem)
                    time.sleep(config.SLEEP_LONG)

                    # 상세 정보 수집
                    event_details = get_all_sub_texts(driver, detail_xpath)
                    status = event_details.get("상태", "-")
                    if not status:
                        raise Exception("상태 정보 없음")

                    # 영향 리소스 수집
                    event_resources = get_affected_resources(client, driver)
                    events.append({
                        "title": event_title,
                        "details": event_details,
                        "affected_resources": event_resources,
                        "status": status
                    })

                    # 상세 팝업 닫기
                    cancel_btn = WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                        EC.element_to_be_clickable((By.XPATH, config.XPATHS['events_page']['cancel_button']))
                    )
                    cancel_btn.click()
                    time.sleep(config.SLEEP_LONG)

                except Exception:
                    continue

        except TimeoutException:
            pass

    return count, events


def get_all_sub_texts(driver, parent_xpath):
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, parent_xpath))
        )
        all_elements_xpath = f"{parent_xpath}//*"
        elements = driver.find_elements(By.XPATH, all_elements_xpath)
        
        all_texts = []
        for element in elements:
            text = element.text.strip()
            if text and text != '-' and text != "이 이벤트에 대한 피드백" and text != "Feedback for this event":
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        all_texts.append(line)
        
        key_mapping = {
            "서비스": "Service",
            "시작 시간": "Start time",
            "상태": "Status",
            "종료 시간": "End time",
            "리전/가용 영역": "Region / Availability Zone",
            "범주": "Category",
            "계정별": "Account specific",
            "영향을 받는 리소스": "Affected resources",
            "설명": "Description"
        }
        kr_keys = list(key_mapping.keys())
        en_keys = list(key_mapping.values())
        
        event_details = {}
        i = 0
        while i < len(all_texts):
            text = all_texts[i]
            matched = False
            
            # 한글 키 먼저 확인
            for kr_key in kr_keys:
                if text == kr_key or text.startswith(kr_key):
                    # 이미 해당 키가 저장되어 있다면 스킵
                    if kr_key in event_details and event_details[kr_key] != "-":
                        matched = True
                        break
                    value = text[len(kr_key):].strip() if text != kr_key else None
                    if not value and i + 1 < len(all_texts):
                        next_text = all_texts[i + 1].strip()
                        if not any(next_text.startswith(k) for k in kr_keys + en_keys):
                            value = next_text
                            i += 1
                    if kr_key == "종료 시간":
                        event_details[kr_key] = "-" if not value or value == "-" else value
                    elif kr_key == "설명":
                        description_lines = [value] if value else []
                        j = i + 1
                        while j < len(all_texts) and not any(all_texts[j].startswith(k) for k in kr_keys + en_keys):
                            description_lines.append(all_texts[j].strip().replace('\\n', '\n'))
                            j += 1
                        event_details[kr_key] = "\n".join(description_lines) if description_lines else "-"
                        i = j - 1
                    else:
                        event_details[kr_key] = value if value else "-"
                    matched = True
                    break
            
            # 영어 키 확인(동일 항목이면 건너뛰도록)
            if not matched:
                for en_key in en_keys:
                    if text == en_key or text.startswith(en_key):
                        kr_key = [k for k, v in key_mapping.items() if v == en_key][0]
                        # 이미 값이 저장되어 있다면 스킵
                        if kr_key in event_details and event_details[kr_key] != "-":
                            matched = True
                            break
                        value = text[len(en_key):].strip() if text != en_key else None
                        if not value and i + 1 < len(all_texts):
                            next_text = all_texts[i + 1].strip()
                            if not any(next_text.startswith(k) for k in kr_keys + en_keys):
                                value = next_text
                                i += 1
                        if kr_key == "종료 시간":
                            event_details[kr_key] = "-" if not value or value == "-" else value
                        elif kr_key == "설명":
                            description_lines = [value] if value else []
                            j = i + 1
                            while j < len(all_texts) and not any(all_texts[j].startswith(k) for k in kr_keys + en_keys):
                                description_lines.append(all_texts[j].strip().replace('\\n', '\n'))
                                j += 1
                            if kr_key not in event_details or event_details[kr_key] == "-":
                                event_details[kr_key] = "\n".join(description_lines) if description_lines else "-"
                            i = j - 1
                        else:
                            event_details[kr_key] = value if value else "-"
                        matched = True
                        break
            
            i += 1
        
        # 누락된 키에 대해 기본값 설정
        for kr_key in kr_keys:
            if kr_key not in event_details:
                event_details[kr_key] = "-"
        
        return event_details
    except Exception as e:
        return {
            "서비스": "-", "시작 시간": "-", "상태": "-", "종료 시간": "-",
            "리전/가용 영역": "-", "범주": "-", "계정별": "-",
            "영향을 받는 리소스": "-", "설명": "-"
        }


def get_affected_resources(client, driver):
    try:
        btn = WebDriverWait(driver, config.EXPLICIT_WAIT).until(
            EC.element_to_be_clickable((By.XPATH, config.XPATHS['affected_resources']['tab']))
        )
        btn.click()
        time.sleep(config.SLEEP_LONG)

        resources = []
        while True:
            for xpath in ['link', 'text']:
                elems = driver.find_elements(By.XPATH, config.XPATHS['affected_resources'][xpath])
                for el in elems:
                    text = el.text.strip()
                    href = el.get_attribute('href') if xpath == 'link' else None
                    if text:
                        resources.append({"text": text, "link": href})

            next_btns = driver.find_elements(By.XPATH, config.XPATHS['affected_resources']['next_button'])
            if next_btns and next_btns[0].is_enabled():
                next_btns[0].click()
                time.sleep(config.SLEEP_LONG)
                continue
            break

        return resources or '-'
    except Exception:
        return '-'


def process_account(client):
    attempts = 1
    while attempts <= 5:
        print(f"{client['name']} 계정 처리 시작... (시도 {attempts}/5)")
        driver = init_driver()
        if not driver:
            return {"name": client['name'], "error": "드라이버 초기화 실패"}

        try:
            aws_login = config.AWS_LOGIN_URL_TEMPLATE.format(account=client['account'])
            driver.get(aws_login)
            time.sleep(config.SLEEP_LONG)
            WebDriverWait(driver, config.PAGE_LOAD_TIMEOUT).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )

            # 로그인
            WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                EC.visibility_of_element_located((By.ID, "username"))
            ).send_keys(client['username'])
            WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                EC.visibility_of_element_located((By.ID, "password"))
            ).send_keys(client['password'])
            WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                EC.element_to_be_clickable((By.ID, "signin_button"))
            ).click()
            print(client['name'], ' id 비밀번호 제출 완료')
            time.sleep(config.SLEEP_LONG)

            # MFA
            mfa_field = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "mfaCode")))
            mfa_field.send_keys(pyotp.TOTP(client['mfaSecret']).now())
            

            WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit'], button.awsui-button"))
            ).click()

            print(client['name'],' OTP 제출 완료')
            time.sleep(config.SLEEP_SHORT)
            WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                EC.any_of(
                    EC.url_contains("console.aws.amazon.com"),
                    EC.presence_of_element_located((By.ID, "aws-console-root"))
                )
            )
            time.sleep(config.SLEEP_LONG)
            print(client['name'], ' AWS 화면 떴음')

            # 알람 페이지 이동
            WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                EC.element_to_be_clickable((By.XPATH, config.XPATHS['login']['alarm_button']))
            ).click()
            time.sleep(config.SLEEP_MEDIUM)
            print(client['name'], ' 알람 페이지 이동 완료')

            time.sleep(config.SLEEP_LONG)
            WebDriverWait(driver, config.EXPLICIT_WAIT).until(
                EC.element_to_be_clickable((By.XPATH, config.XPATHS['login']['all_events_button']))
            ).click()
            time.sleep(config.SLEEP_LONG)

            # 이벤트 수집
            unresolved_count, unresolved_events = get_count_and_events(
                client, driver,
                "미해결 문제 및 최근 문제",
                config.XPATHS['events_page']['unresolved']['count'],
                config.XPATHS['events_page']['unresolved']['button'],
                config.XPATHS['events_page']['tbody'],
                config.XPATHS['events_page']['detail']
            )
            scheduled_count, scheduled_events = get_count_and_events(
                client, driver,
                "예정된 변경 사항",
                config.XPATHS['events_page']['scheduled']['count'],
                config.XPATHS['events_page']['scheduled']['button'],
                config.XPATHS['events_page']['tbody'],
                config.XPATHS['events_page']['detail']
            )
            other_count, other_events = get_count_and_events(
                client, driver,
                "기타 알림",
                config.XPATHS['events_page']['other']['count'],
                config.XPATHS['events_page']['other']['button'],
                config.XPATHS['events_page']['tbody'],
                config.XPATHS['events_page']['detail']
            )

            all_events = unresolved_events + scheduled_events + other_events
            result = {
                "name": client['name'],
                "account_id": client['account'],
                "unresolved_count": unresolved_count,
                "scheduled_count": scheduled_count,
                "other_count": other_count,
                "events": {"unresolved": unresolved_events, "scheduled": scheduled_events, "other": other_events}
            }
            if not all_events:
                result['events'] = {"unresolved": [{"title":"-","details":{},"affected_resources":"-","status":"-"}]}

            driver.quit()
            return result

        except Exception as e:
            print(client['name'], '에러 발생:', e)
            driver.quit()
            attempts += 1
            time.sleep(config.SLEEP_MEDIUM)

    return {"name": client['name'], "error": "최대 시도 횟수 초과"}


def main():
    start = time.time()
    clients = load_clients_from_sheets(config.SHEET_TITLE)
    if not clients:
        return

    all_results = []
    with ThreadPoolExecutor(max_workers=config.MAX_THREAD) as executor:
        futures = {executor.submit(process_account, c): c for c in clients}
        for fut in as_completed(futures):
            client = futures[fut]
            try:
                res = fut.result()
                sheet_name, records = format_event_to_df(res)
                all_results.append((sheet_name, records))
            except Exception as e:
                log_failed_client(client['name'], str(e))

    save_all_to_sqlite(all_results)
    print("총 걸린 시간:", time.time() - start)


if __name__ == '__main__':
    main()
