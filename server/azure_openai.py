import os
import json
import hashlib
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from openai import AzureOpenAI
from cachetools import TTLCache
import logging
import config

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# .env 파일 로드
load_dotenv()

# Azure OpenAI API 설정
endpoint = os.getenv('AZURE_OPENAI_ENDPOINT', 'https://hoseop-test-ai.openai.azure.com/')
deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o-mini')
api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-12-01-preview')
subscription_key = os.getenv('AZURE_OPENAI_API_KEY')

# Azure OpenAI 클라이언트 초기화
client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key
)

# 메모리 캐시 설정
cache = TTLCache(maxsize=1000, ttl=24 * 60 * 60)

# DB 경로
DB_PATH = config.DB_PATH

# SQLite 데이터베이스 초기화
def init_db():
    try:
        conn = sqlite3.connect('event_cache.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_cache (
                cache_key TEXT PRIMARY KEY,
                event_title TEXT,
                event_description TEXT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        logger.info("event_cache 테이블 생성 또는 확인 완료")
    except sqlite3.Error as e:
        logger.error(f"데이터베이스 초기화 실패: {str(e)}")
        raise Exception(f"데이터베이스 초기화 실패: {str(e)}")
    finally:
        conn.close()

# 캐시 키 생성
def generate_cache_key(event_title, event_description):
    return hashlib.md5((event_title + event_description).encode()).hexdigest()

# SQLite에서 캐시 조회
def get_cached_summary(cache_key):
    try:
        conn = sqlite3.connect('event_cache.db')
        cursor = conn.cursor()
        cursor.execute('SELECT summary FROM event_cache WHERE cache_key = ?', (cache_key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except sqlite3.Error as e:
        logger.error(f"캐시 조회 실패: {str(e)}")
        raise Exception(f"캐시 조회 실패: {str(e)}")

# SQLite에 캐시 저장
def save_cached_summary(cache_key, event_title, event_description, summary):
    try:
        conn = sqlite3.connect('event_cache.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO event_cache (cache_key, event_title, event_description, summary)
            VALUES (?, ?, ?, ?)
        ''', (cache_key, event_title, event_description, summary))
        conn.commit()
        logger.info(f"캐시 저장 완료: cache_key={cache_key}")
    except sqlite3.Error as e:
        logger.error(f"캐시 저장 실패: {str(e)}")
        raise Exception(f"캐시 저장 실패: {str(e)}")
    finally:
        conn.close()

# 모든 캐시 삭제
def clear_all_caches():
    try:
        cache.clear()
        conn = sqlite3.connect('event_cache.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM event_cache')
        conn.commit()
        logger.info("모든 캐시 삭제 완료")
    except sqlite3.Error as e:
        logger.error(f"캐시 삭제 실패: {str(e)}")
        raise Exception(f"캐시 삭제 실패: {str(e)}")
    finally:
        conn.close()

# 특정 이벤트 캐시 삭제
def clear_event_cache(event_id, db_path='events.db'):
    try:
        event_data = get_event_data(event_id, db_path)
        event_title = event_data['event_title']
        event_description = event_data['event_description']
        cache_key = generate_cache_key(event_title, event_description)
        
        if cache_key in cache:
            del cache[cache_key]
            logger.info(f"메모리 캐시 삭제: cache_key={cache_key}")
        
        conn = sqlite3.connect('event_cache.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM event_cache WHERE cache_key = ?', (cache_key,))
        conn.commit()
        logger.info(f"SQLite 캐시 삭제: cache_key={cache_key}")
    except sqlite3.Error as e:
        logger.error(f"이벤트 캐시 삭제 실패: {str(e)}")
        raise Exception(f"이벤트 캐시 삭제 실패: {str(e)}")
    finally:
        conn.close()

# 템플릿 정의
template = """안녕하세요.
베스핀글로벌 입니다.

{account_ids} 계정에서 {event_name} 발생하여 내용 전달드립니다.

1) 이벤트 내용
{event_description}

2) 이벤트 대상
{affected_resources}

3) 이벤트 시간
{event_time}

관련하여 문의사항 있으시거나 지원이 필요하시다면 회신 부탁드립니다.

감사합니다.
베스핀글로벌 드림
"""

# 이벤트 설명 요약 함수
def summarize_event_description(event_description, event_title):
    cache_key = generate_cache_key(event_title, event_description)
    
    if cache_key in cache:
        logger.info(f"메모리 캐시 히트: cache_key={cache_key}")
        return cache[cache_key]
    
    cached_summary = get_cached_summary(cache_key)
    if cached_summary:
        cache[cache_key] = cached_summary
        logger.info(f"SQLite 캐시 히트: cache_key={cache_key}")
        return cached_summary
    
    prompt = f"""
다음 이벤트 설명을 3~6문장으로 간결하게 요약하되, 핵심 정보만 포함하고 아래 예시처럼 간단한 문장으로 작성해 주세요.
각 문장은 줄바꿈으로 구분하고, 각 문장 앞에 공백 3칸과 대시('   -')를 붙여 주세요.
링크와 세부적인 기술적 세부사항은 제외하고, 주요 이벤트 내용, 날짜, 권장 조치, 대상 버전 등을 중심으로 요약하세요.
AWS의 한국어 안내 스타일을 따라, '귀하', '귀하신' 같은 표현 대신 '고객님' 또는 직설적인 문장(예: 'ap-northeast-2 지역에서...')을 사용하세요.
입력 설명의 기존 대시('-') 또는 기타 접두사는 완전히 무시하고, 모든 문장에 새로운 '   -'를 적용하세요.
마크다운 형식을 사용하지 말고 일반 텍스트로 작성하세요.

예시:
   - AWS Lambda에서 Node.js 18 런타임 지원이 2025년 9월 1일에 종료됩니다.
   - Node.js 18 함수는 최신 런타임으로 업그레이드하는 것이 권장됩니다.
   - 지원 종료 후 함수는 실행되지만 패치가 제공되지 않습니다.
   - 영향을 받는 함수는 AWS 콘솔에서 확인할 수 있습니다.

이벤트 제목: {event_title}
설명:
{event_description}
"""
    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that summarizes technical event descriptions into concise, clear, and professional Korean text, following AWS's Korean style guidelines. Use '고객님' or direct sentences instead of '귀하' or '귀하신'. Ignore all existing dashes or prefixes in the input and apply '   -' to all sentences. Focus on key information and recommended actions. Do not use markdown formatting."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=500,
            temperature=0.5,
            top_p=1.0,
            model=deployment
        )
        summary = response.choices[0].message.content.strip()
        logger.debug(f"Generated summary: {summary}")
        
        cache[cache_key] = summary
        save_cached_summary(cache_key, event_title, event_description, summary)
        logger.info(f"새 요약 생성 및 캐시 저장: cache_key={cache_key}")
        
        return summary
    except Exception as e:
        logger.error(f"Azure OpenAI API 요약 생성 실패: {str(e)}")
        raise Exception(f"Azure OpenAI API 요약 생성 실패: {str(e)}")

# 입력 데이터를 처리하여 템플릿에 맞게 포맷팅
def format_event_data(event_data):
    import re  # re 모듈 임포트 추가
    try:
        logger.info(f"Formatting event data for event_id={event_data['id']}")
        event_id = event_data['id']
        event_title = event_data['event_title'] or "제목 없음"
        event_description = event_data['event_description'] or ""
        region = event_data['region'] or "미지정"
        affected_resources_json = event_data.get('affected_resources', '[]')
        event_name = event_data.get('event_name', 'AWS Event')
        account_ids = event_data.get('account_ids', 'AWS 계정')
        event_time = event_data.get('event_time', '미정')
        
        # event_description 요약
        summarized_description = summarize_event_description(event_description, event_title)
        # 모든 줄에 '   -'가 적용되도록 정규화
        description_lines = summarized_description.split('\n')
        normalized_description = '\n'.join(
            f"   - {line[4:].lstrip('- ').strip()}" if line.startswith('   -') else f"   - {line.lstrip('- ').strip()}"
            for line in description_lines if line.strip()
        )
        logger.debug(f"Normalized description: {normalized_description}")
        
        # affected_resources 처리
        resources_str = "리소스 정보 없음"
        try:
            resources = json.loads(affected_resources_json)
            if not isinstance(resources, list):
                raise ValueError("affected_resources는 JSON 배열이어야 합니다.")
            if not resources:
                resources_str = "영향을 받는 리소스 없음"
            else:
                resources_str = ""
                for res in resources:
                    resource_text = res.get('text', 'Unknown')
                    engine_version = res.get('engine_version')
                    if engine_version and engine_version != '':
                        resources_str += f"   - {resource_text} (엔진버전: {engine_version})\n"
                    else:
                        resources_str += f"   - {resource_text}\n"
        except json.JSONDecodeError as e:
            resources_str = f"리소스 파싱 오류: {str(e)}"
        except ValueError as e:
            resources_str = f"리소스 형식 오류: {str(e)}"
        
        clean_time = event_time.replace(" UTC+9", "").replace("시간 ", "").strip()
        
        try:
            # 1. '2025년 4월 15일 11:28:00 오전' 형식 시도
            clean_time = clean_time.replace("오전", "AM").replace("오후", "PM")
            parsed_time = datetime.strptime(clean_time, "%Y년 %m월 %d일 %I:%M:%S %p")
            formatted_time = parsed_time.strftime("%Y년 %m월 %d일 %p %I:%M").replace("AM", "오전").replace("PM", "오후")
            logger.debug(f"Parsed Korean format: {formatted_time}")
        except (ValueError, TypeError):
            try:
                # 3. 'June 30, 2025 at 5:00:00 PM UTC+9' 형식 시도
                # UTC+9와 같은 시간대 정보 제거
                clean_time = re.sub(r'\s*UTC[+-]\d+', '', event_time)
                
                # '오전' -> 'AM', '오후' -> 'PM' 변환
                clean_time = clean_time.replace("오전", "AM").replace("오후", "PM")
                
                # 날짜와 시간 파싱
                parsed_time = datetime.strptime(clean_time.strip(), "%B %d, %Y at %I:%M:%S %p")
                
                # 원하는 형식으로 변환
                formatted_time = parsed_time.strftime("%Y년 %m월 %d일 %p %I:%M").replace("AM", "오전").replace("PM", "오후")
                logger.debug(f"Parsed English format: {formatted_time}")
            except (ValueError, TypeError) as e:
                # 4. 실패 시 원본에서 시간 부분만 추출
                logger.warning(f"시간 파싱 실패: {str(e)}, 원본: {event_time}")
                time_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', event_time)
                formatted_time = f"{time_match.group(1)} (원본: {event_time})" if time_match else event_time

        formatted_time = f"   - {formatted_time}"
        
        # 템플릿에 데이터 삽입
        formatted_message = template.format(
            account_ids=account_ids,
            event_name=event_name,
            event_description=normalized_description,
            affected_resources=resources_str.rstrip(),
            event_time=formatted_time
        )
        # 앞뒤 공백과 줄바꿈 제거
        return formatted_message.strip()
    except KeyError as e:
        logger.error(f"필수 데이터 누락: {str(e)}")
        raise Exception(f"필수 데이터 누락: {str(e)}")
    except Exception as e:
        logger.error(f"데이터 포맷팅 실패: {str(e)}")
        raise Exception(f"데이터 포맷팅 실패: {str(e)}")

# 데이터베이스에서 이벤트 데이터 조회
def get_event_data(event_id, db_path=DB_PATH):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.event_id, e.title, e.description, e.region, e.affected_resources_list,
                   e.start_time, c.account_id, e.event_type
            FROM events e 
            JOIN clients c ON e.client_id = c.client_id 
            WHERE e.event_id = ?
        """, (event_id,))
        event = cursor.fetchone()
        conn.close()
        
        if not event:
            raise Exception(f"Event ID {event_id}를 찾을 수 없습니다")
        
        return {
            "id": event[0],
            "event_name": event[1] or "AWS Event",
            "event_title": event[1] or "제목 없음",
            "event_description": event[2] or "",
            "region": event[3] or "미지정",
            "affected_resources": event[4] or "[]",
            "event_time": event[5] or "미정",
            "account_ids": event[6] or "Unknown"
        }
    except sqlite3.Error as e:
        logger.error(f"데이터베이스 조회 실패: {str(e)}")
        raise Exception(f"데이터베이스 조회 실패: {str(e)}")
    except Exception as e:
        logger.error(f"이벤트 데이터 조회 실패: {str(e)}")
        raise Exception(f"이벤트 데이터 조회 실패: {str(e)}")

# 초기화
init_db()