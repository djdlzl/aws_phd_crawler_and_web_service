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
import threading
from config import (
    CHROMEDRIVER_PATH, AWS_LOGIN_URL_TEMPLATE, MAX_THREAD, INTERFERING_SPAN_SELECTOR, XPATHS, KEY_MAPPING
)

def get_count_and_events(client, driver, section_name, count_xpath, button_xpath, tbody_xpath, detail_xpath):
    try:
        link = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, count_xpath))
        )
        count_text = link.text.strip()
        count = int(re.search(r'\d+', count_text).group() if re.search(r'\d+', count_text) else '0')
    except TimeoutException:
        count = 0

    events = []
    if count > 0:
        try:
            button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, button_xpath))
            )
            button.click()
            time.sleep(4)

            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, tbody_xpath)))
            rows = driver.find_elements(By.XPATH, f"{tbody_xpath}/tr")
            if not rows:
                return count, events

            for row in rows:
                try:
                    event_link_elements = row.find_elements(By.XPATH, "./td[2]/div/a")
                    if not event_link_elements:
                        continue
                    event_link = event_link_elements[0]
                    event_title = event_link.text.strip()
                    if not event_title:
                        continue

                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", event_link)
                    driver.execute_script("window.scrollBy(0, -100);")
                    try:
                        interfering_span = driver.find_element(By.CSS_SELECTOR, INTERFERING_SPAN_SELECTOR)
                        driver.execute_script("arguments[0].style.display = 'none';", interfering_span)
                        event_link = row.find_element(By.XPATH, "./td[2]/div/a")
                        driver.execute_script("arguments[0].click();", event_link)
                    except Exception:
                        continue

                    time.sleep(5)
                    event_details = get_all_sub_texts(driver, detail_xpath)

                    status = event_details.get("상태", "-")
                    if not event_title or not status:
                        time.sleep(4)
                        cancel_button_xpath = XPATHS["events_page"]["cancel_button"]
                        cancel_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, cancel_button_xpath)))
                        cancel_button.click()
                        time.sleep(5)
                        continue

                    event_resources = get_affected_resources(client, driver)
                    events.append({
                        "title": event_title,
                        "details": event_details,
                        "affected_resources": event_resources if event_resources else "-",
                        "status": status
                    })

                    time.sleep(4)
                    cancel_button_xpath = XPATHS["events_page"]["cancel_button"]
                    cancel_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, cancel_button_xpath)))
                    cancel_button.click()
                    time.sleep(5)

                except Exception as e:
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
        kr_keys = list(KEY_MAPPING.keys())
        en_keys = list(KEY_MAPPING.values())
        event_details = {}
        i = 0
        while i < len(all_texts):
            text = all_texts[i]
            matched = False
            # 한글 키 먼저 확인
            for kr_key in kr_keys:
                if text == kr_key or text.startswith(kr_key):
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
                        kr_key = [k for k, v in KEY_MAPPING.items() if v == en_key][0]
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
        for kr_key in kr_keys:
            if kr_key not in event_details:
                event_details[kr_key] = "-"
        return event_details
    except Exception as e:
        return {k: "-" for k in KEY_MAPPING.keys()}

def get_affected_resources(client, driver):
    affected_resources_tab_xpath = XPATHS["affected_resources"]["tab"]
    affected_resources_link_xpath = XPATHS["affected_resources"]["link"]
    affected_resources_text_xpath = XPATHS["affected_resources"]["text"]
    next_button_xpath = XPATHS["affected_resources"]["next_button"]
    try:
        affected_resources_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, affected_resources_tab_xpath))
        )
        affected_resources_button.click()
        time.sleep(5)
        affected_resources = []
        while True:
            link_elements = driver.find_elements(By.XPATH, affected_resources_link_xpath)
            for elem in link_elements:
                resource_text = elem.text.strip()
                resource_link = elem.get_attribute("href")
                if resource_text:
                    affected_resources.append({"text": resource_text, "link": resource_link})
            text_elements = driver.find_elements(By.XPATH, affected_resources_text_xpath)
            for elem in text_elements:
                resource_text = elem.text.strip()
                if resource_text:
                    affected_resources.append({"text": resource_text, "link": None})
            next_buttons = driver.find_elements(By.XPATH, next_button_xpath)
            if next_buttons and next_buttons[0].is_enabled():
                next_buttons[0].click()
                time.sleep(5)
            else:
                break
        return affected_resources if affected_resources else "-"
    except Exception as e:
        return "-"

def process_account(client, chromedriver_path):
    max_attempts = 3
    attempt = 1
    while attempt <= max_attempts:
        print(f"{client['name']} 계정 처리 시작... (시도 {attempt}/{max_attempts})")
        options = webdriver.ChromeOptions()
        # options.add_argument("headless")
        options.add_argument('--disable-gpu') 
        options.add_experimental_option("detach", True)
        options.add_argument('--start-maximized')
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        try:
            aws_login_url = AWS_LOGIN_URL_TEMPLATE.format(account=client['account'])
            driver.get(aws_login_url)
            time.sleep(3)
            WebDriverWait(driver, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
            username_field = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "username")))
            username_field.send_keys(client['username'])
            password_field = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "password")))
            password_field.send_keys(client['password'])
            signin_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signin_button")))
            signin_button.click()
            time.sleep(3)


            mfa_field = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "mfaCode")))
            totp = pyotp.TOTP(client['mfaSecret'])
            mfa_code = totp.now()
            mfa_field.send_keys(mfa_code)
            

            submit_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit'], button.awsui-button")))
            submit_button.click()
            
            time.sleep(3)
            WebDriverWait(driver, 15).until(EC.any_of(EC.url_contains("console.aws.amazon.com"), EC.presence_of_element_located((By.ID, "aws-console-root"))))
            time.sleep(5)
            alarm_button_selector = XPATHS["login"]["alarm_button"]
            print(client['name'], ': 알람 버튼 경로 확인 완료')
            time.sleep(8)
            alarm_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, alarm_button_selector)))
            alarm_button.click()
            time.sleep(0.5)
            all_events_button_xpath = XPATHS["login"]["all_events_button"]
            all_events_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, all_events_button_xpath)))
            all_events_button.click()
            time.sleep(5)
            unresolved_issues_count_xpath = XPATHS["events_page"]["unresolved"]["count"]
            unresolved_issues_button_xpath = XPATHS["events_page"]["unresolved"]["button"]
            scheduled_changes_count_xpath = XPATHS["events_page"]["scheduled"]["count"]
            scheduled_changes_button_xpath = XPATHS["events_page"]["scheduled"]["button"]
            other_notifications_count_xpath = XPATHS["events_page"]["other"]["count"]
            other_notifications_button_xpath = XPATHS["events_page"]["other"]["button"]
            tbody_xpath = XPATHS["events_page"]["tbody"]
            detail_xpath = XPATHS["events_page"]["detail"]
            unresolved_count, unresolved_events = get_count_and_events(client, driver, "미해결 문제 및 최근 문제", unresolved_issues_count_xpath, unresolved_issues_button_xpath, tbody_xpath, detail_xpath)
            scheduled_count, scheduled_events = get_count_and_events(client, driver, "예정된 변경 사항", scheduled_changes_count_xpath, scheduled_changes_button_xpath, tbody_xpath, detail_xpath)
            other_count, other_events = get_count_and_events(client, driver, "기타 알림", other_notifications_count_xpath, other_notifications_button_xpath, tbody_xpath, detail_xpath)
            total_events = unresolved_events + scheduled_events + other_events
            result = {
                "name": client["name"],
                "account_id": client["account"],
                "unresolved_count": unresolved_count,
                "scheduled_count": scheduled_count,
                "other_count": other_count,
                "events": {
                    "unresolved": unresolved_events,
                    "scheduled": scheduled_events,
                    "other": other_events,
                }
            }
            if not total_events:
                result["events"] = {"unresolved": [{"title": "-", "details": {}, "affected_resources": "-", "status": "-"}]}
            driver.quit()
            return result
        except Exception as e:
            driver.quit()
            attempt += 1
            if attempt > max_attempts:
                return {"name": client["name"], "error": f"최대 시도 횟수 초과: {str(e)}"}
            time.sleep(3)

def main():
    start_time = time.time()
    sheet_title = "SRE1_자동화 고객사 목록"
    clients = load_clients_from_sheets(sheet_title)
    if not clients:
        return
    chromedriver_path = CHROMEDRIVER_PATH
    all_results = []
    with ThreadPoolExecutor(max_workers=MAX_THREAD) as executor:
        future_to_client = {executor.submit(process_account, client, chromedriver_path): client for client in clients}
        for future in as_completed(future_to_client):
            client = future_to_client[future]
            try:
                result = future.result()
                sheet_name, records = format_event_to_df(result)
                all_results.append((sheet_name, records))
            except Exception as e:
                log_failed_client(client['name'], str(e))
    save_all_to_sqlite(all_results)
    end_time = time.time()
    print("총 걸린 시간: ", end_time - start_time)

if __name__ == "__main__":
    main()