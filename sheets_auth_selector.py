import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
import os
import config


def setup_missing_logger():
    """
    누락된 클라이언트 로깅을 위한 파일 핸들러 설정
    """
    log_path = os.path.join(os.getcwd(), config.MISSING_CLIENTS_LOG_FILE)
    
    logger = logging.getLogger(config.MISSING_CLIENTS_LOGGER_NAME)
    logger.setLevel(config.MISSING_CLIENTS_LOG_LEVEL)

    if not logger.handlers:
        handler = logging.FileHandler(log_path, mode=config.MISSING_CLIENTS_LOG_MODE, encoding='utf-8')
        formatter = logging.Formatter(config.MISSING_CLIENTS_LOG_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def load_clients_from_sheets(sheet_title):
    logger = setup_missing_logger()

    # gspread 인증
    scope = config.GSHEET_SCOPE
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        config.GOOGLE_CREDENTIALS_FILE,
        scope
    )
    client = gspread.authorize(creds)

    sheet = client.open(sheet_title).sheet1
    raw_data = sheet.get_values(config.SHEET_RANGE)

    parsed_clients = []
    latest_company = None

    for row in raw_data:
        company = row[1].strip() if len(row) > 1 and row[1] else None
        env = row[3].strip() if len(row) > 3 and row[3] else None

        if not company and not env:
            continue

        if company:
            latest_company = company
        else:
            company = latest_company

        detail = row[2].strip() if len(row) > 2 else ""
        full_name = f"{company}-{env}-{detail}"

        # 제외 키워드 체크
        if any(kw in full_name for kw in config.EXCLUDE_KEYWORDS):
            print(f"제외됨: {full_name}")
            continue

        # 필수 필드 추출
        username   = row[4].strip() if len(row) > 4 and row[4] else ""
        password   = row[5].strip() if len(row) > 5 and row[5] else ""
        account    = row[6].strip() if len(row) > 6 and row[6] else ""
        mfa_secret = row[7].strip() if len(row) > 7 and row[7] else ""

        missing = []
        if not username:   missing.append("IAM 사용자")
        if not password:   missing.append("비밀번호")
        if not account:    missing.append("Account ID")
        if not mfa_secret: missing.append("MFA Secret")

        if missing:
            logger.info(f"{full_name} - 누락 항목: {', '.join(missing)}")
            continue

        parsed_clients.append({
            "name":      full_name,
            "username":  username,
            "password":  password,
            "account":   account,
            "mfaSecret": mfa_secret
        })

    return parsed_clients
