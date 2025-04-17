import requests
import json
import os
import config


def format_event_to_df(client_result):
    sheet_name = client_result.get("name", "Unknown")
    account_id = client_result.get("account_id", "Unknown")
    records = []
    for event_type, events in client_result.get("events", {}).items():
        for event in events:
            details = event.get("details", {})
            row = {
                "client_name": sheet_name,
                "account_id": account_id,
                "title": event.get("title", "-"),
                "event_type": event_type,
                "status": event.get("status", "-"),
                "details": json.dumps({
                    "서비스": details.get("서비스", "-"),
                    "시작 시간": details.get("시작 시간", "-"),
                    "종료 시간": details.get("종료 시간", "-"),
                    "리전/가용 영역": details.get("리전/가용 영역", "-"),
                    "범주": details.get("범주", "-"),
                    "계정별": details.get("계정별", "-"),
                    "영향을 받는 리소스": details.get("영향을 받는 리소스", "-"),
                    "설명": details.get("설명", "-")
                }, ensure_ascii=False),
                "affected_resources": json.dumps(event.get("affected_resources", "-"), ensure_ascii=False)
            }
            records.append(row)
    print(f"Client '{sheet_name}' 데이터: {len(records)} 행")
    return sheet_name, records

def save_all_to_sqlite(all_results):
    if not all_results:
        print("저장할 데이터가 없습니다.")
        return

    payload = {"results": all_results}
    try:
        response = requests.post(config.WEB_SERVER_URL, json=payload)
        if response.status_code == 200:
            print("웹서버에 데이터 저장 완료")
        else:
            print(f"웹웹서버 저장 실패: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"웹서버 저장 중 오류: {str(e)}")

def log_failed_client(client_name, error_msg):
    log_path = os.path.join(os.getcwd(), "failed_clients.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{client_name} - 실패 이유: {error_msg}\n")