from flask import Flask, request, jsonify, render_template
import sqlite3
import json
from datetime import datetime
import os
import config

app = Flask(__name__)
DB_PATH = config.DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            account_id TEXT NOT NULL,
            last_crawled TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            title TEXT,
            event_type TEXT,
            service TEXT,
            start_time TEXT,
            status TEXT,
            end_time TEXT,
            region TEXT,
            category TEXT,
            account_specific TEXT,
            affected_resources_text TEXT,
            description TEXT,
            affected_resources_list TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            crawled_at TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(client_id)
        )
    """)
    conn.commit()
    conn.close()

def compare_events(existing_event, new_event, details, affected_resources):
    """이벤트 데이터가 동일한지 비교"""
    fields_to_compare = [
        ("title", new_event["title"] if new_event["title"] and new_event["title"] != '-' else None),
        ("event_type", new_event["event_type"]),
        ("service", details.get("서비스", "-")),
        ("start_time", details.get("시작 시간", "-")),
        ("status", details.get("상태", "-")),
        ("end_time", details.get("종료 시간", "-")),
        ("region", details.get("리전/가용 영역", "-")),
        ("category", details.get("범주", "-")),
        ("account_specific", details.get("계정별", "-")),
        ("affected_resources_text", details.get("영향을 받는 리소스", "-")),
        ("description", details.get("설명", "-")),
        ("affected_resources_list", affected_resources)
    ]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/events', methods=['POST'])
def save_events():
    try:
        data = request.json
        all_results = data.get('results', [])
        if not all_results:
            return jsonify({"message": "저장할 데이터가 없습니다."}), 400

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        for sheet_name, records in all_results:
            if not records:
                continue

            account_id = next((record.get("account_id") for record in records if record.get("account_id") != "Unknown"), "Unknown")

            cursor.execute("SELECT client_id FROM clients WHERE name = ?", (sheet_name,))
            client_row = cursor.fetchone()
            if client_row:
                client_id = client_row[0]
                cursor.execute("UPDATE clients SET last_crawled = ?, account_id = ? WHERE client_id = ?",
                              (current_time, account_id, client_id))
            else:
                cursor.execute("INSERT INTO clients (name, account_id, last_crawled) VALUES (?, ?, ?)",
                              (sheet_name, account_id, current_time))
                client_id = cursor.lastrowid

            # 기존 이벤트 가져오기
            cursor.execute("""
                SELECT event_id, title, event_type, service, start_time, status, end_time, 
                       region, category, account_specific, affected_resources_text, 
                       description, affected_resources_list
                FROM events 
                WHERE client_id = ? AND title IS NOT NULL AND title != '-'
            """, (client_id,))
            existing_events = {row[1]: dict(event_id=row[0], title=row[1], event_type=row[2],
                                         service=row[3], start_time=row[4], status=row[5],
                                         end_time=row[6], region=row[7], category=row[8],
                                         account_specific=row[9], affected_resources_text=row[10],
                                         description=row[11], affected_resources_list=row[12])
                             for row in cursor.fetchall()}
            current_titles = set()

            for record in records:
                title = record["title"] if record["title"] and record["title"] != '-' else None
                details = json.loads(record["details"]) if record["details"] else {}
                affected_resources = record["affected_resources"]

                if title:
                    current_titles.add(title)
                    existing_event = existing_events.get(title)

                    if existing_event and existing_event["event_type"] == record["event_type"]:
                        # 동일한 이벤트가 존재하면 데이터 비교
                        if compare_events(existing_event, record, details, affected_resources):
                            continue  # 동일하면 pass
                        else:
                            # 데이터가 다르면 업데이트
                            cursor.execute("""
                                UPDATE events 
                                SET service = ?, start_time = ?, status = ?, end_time = ?, region = ?, 
                                    category = ?, account_specific = ?, affected_resources_text = ?, 
                                    description = ?, affected_resources_list = ?, updated_at = ?, 
                                    crawled_at = ?
                                WHERE event_id = ?
                            """, (
                                details.get("서비스", "-"),
                                details.get("시작 시간", "-"),
                                details.get("상태", "-"),
                                details.get("종료 시간", "-"),
                                details.get("리전/가용 영역", "-"),
                                details.get("범주", "-"),
                                details.get("계정별", "-"),
                                details.get("영향을 받는 리소스", "-"),
                                details.get("설명", "-"),
                                affected_resources,
                                current_time,
                                current_time,
                                existing_event["event_id"]
                            ))
                    else:
                        # 새로운 이벤트 삽입
                        cursor.execute("""
                            INSERT INTO events (
                                client_id, title, event_type, service, start_time, status, end_time, 
                                region, category, account_specific, affected_resources_text, 
                                description, affected_resources_list, created_at, updated_at, crawled_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            client_id,
                            title,
                            record["event_type"],
                            details.get("서비스", "-"),
                            details.get("시작 시간", "-"),
                            details.get("상태", "-"),
                            details.get("종료 시간", "-"),
                            details.get("리전/가용 영역", "-"),
                            details.get("범주", "-"),
                            details.get("계정별", "-"),
                            details.get("영향을 받는 리소스", "-"),
                            details.get("설명", "-"),
                            affected_resources,
                            current_time,
                            current_time,
                            current_time
                        ))

            # 콘솔에서 사라진 이벤트 삭제
            for title in existing_events:
                if title not in current_titles:
                    cursor.execute("DELETE FROM events WHERE event_id = ?",
                                 (existing_events[title]["event_id"],))

        conn.commit()
        conn.close()
        return jsonify({"message": "데이터 저장 및 동기화 완료"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/clients', methods=['GET'])
def get_clients():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.client_id, c.name, c.account_id, c.last_crawled,
                   COALESCE((
                       SELECT json_group_array(
                           json_object(
                               'event_id', e.event_id,
                               'title', e.title,
                               'event_type', e.event_type,
                               'service', e.service,
                               'start_time', e.start_time,
                               'status', e.status,
                               'end_time', e.end_time,
                               'region', e.region,
                               'category', e.category,
                               'account_specific', e.account_specific,
                               'affected_resources_text', e.affected_resources_text,
                               'description', e.description,
                               'affected_resources_list', e.affected_resources_list,
                               'crawled_at', e.crawled_at
                           )
                       )
                       FROM events e
                       WHERE e.client_id = c.client_id AND e.title IS NOT NULL AND e.title != '-'
                   ), '[]') as events
            FROM clients c
            ORDER BY c.name
        """)
        clients = [
            {
                "client_id": row[0],
                "name": row[1],
                "account_id": row[2],
                "last_crawled": row[3],
                "events": json.loads(row[4])
            }
            for row in cursor.fetchall()
        ]
        conn.close()
        return jsonify(clients)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    app.run(host=config.APP_HOST, port=config.APP_PORT)