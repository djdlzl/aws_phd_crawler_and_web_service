# AWS PHD 통합 대시보드

## 개요
`aws phd crawler and web service` 프로젝트는 여러 AWS 계정의 Personal Health Dashboard(PHD) 이벤트를 크롤링하여 SQLite 데이터베이스에 저장하고, Flask 기반 웹 서비스로 조회할 수 있게 구성된 애플리케이션입니다.

주요 구성 요소:
- **Crawler**: Selenium을 사용하여 AWS 콘솔의 PHD 이벤트를 자동으로 크롤링
- **Web Service**: Flask로 구현된 REST API 및 간단한 웹 UI
- **데이터 저장소**: SQLite 데이터베이스(`aws_events.db`)

## 기능
- AWS PHD 미해결 이슈, 예정된 변경 사항, 기타 알림 크롤링
- 이벤트 세부 정보(서비스, 시작/종료 시간, 상태, 영향받는 리소스, 설명 등) 저장
- 클라이언트(고객사)별 이벤트 목록 조회 API 및 웹 UI 제공

## 아키텍처
```text
┌──────────────┐       ┌────────────────────────┐      ┌───────────────┐
│ Crawling Job │ ───▶ │ SQLite (aws_events.db) │ ◀─── │ Flask API/Web │
└──────────────┘       └────────────────────────┘      └───────────────┘
```

## 설치 및 실행

### 1. 환경 요구사항
- Python 3.8 이상
- Chrome 133.x (브라우저 버전과 ChromeDriver 버전 일치 필수)
- ChromeDriver (Chrome 버전에 맞게 설치)
- Linux 환경 권장

### 2. 크롬드라이버 설정
1. [ChromeDriver 다운로드](https://sites.google.com/chromium.org/driver/)에서 사용 중인 Chrome 버전에 맞는 드라이버를 받습니다.
2. 다운로드한 `chromedriver` 실행 파일에 실행 권한을 부여하고, 프로젝트 루트 디렉터리에 위치시킵니다.
   ```bash
   chmod +x chromedriver
   ```

### 3. Python 패키지 설치
프로젝트 루트에서 가상환경을 생성한 뒤, 필요한 패키지를 설치합니다.
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. 데이터베이스 초기화
Flask 앱을 실행하기 전에 데이터베이스를 초기화합니다. (SQLite 파일 `aws_events.db` 생성 및 테이블 생성)
```bash
python3 main.py --init-db
```
또는 애플리케이션 시작 시 자동으로 초기화되도록 `app.before_first_request(init_db)`를 설정할 수 있습니다.

### 5. Crawler 실행
크롤러 스크립트를 실행하여 AWS PHD 데이터를 수집하고 웹 서비스에 저장합니다.
```bash
python3 crawler.py
```

### 6. 웹 서비스 실행
Flask 앱을 Gunicorn으로 실행합니다.
```bash
gunicorn --bind 0.0.0.0:8000 main:app
```
웹 브라우저에서 `http://<서버_IP>:8000` 으로 접속하여 UI 또는 `/api/clients`, `/api/events` 엔드포인트를 확인할 수 있습니다.

## 설정
- AWS 계정 정보는 `sheets_auth_selector.py` 또는 환경 변수로 설정
- MFA(2FA) 토큰은 `pyotp` 기반으로 자동 생성

## 디버깅 및 주의사항
- Headless 모드: ChromeOptions에 다음 옵션 추가 권장
  ```python
  chrome_options.add_argument("--no-sandbox")
  chrome_options.add_argument("--disable-dev-shm-usage")
  chrome_options.add_argument("window-size=1920,1080")
  ```
- Chrome/ChromeDriver 버전 불일치 시 세션 생성 오류 발생 가능
- 멀티스레드 실행 시 리소스 부족 문제 주의

## 라이선스
MIT License

