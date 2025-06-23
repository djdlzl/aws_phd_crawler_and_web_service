import logging
########## main.py ##########
########## main.py ##########
########## main.py ##########

# Paths
CHROMEDRIVER_PATH = "chromedriver.exe"

# AWS
AWS_LOGIN_URL_TEMPLATE = "https://{account}.signin.aws.amazon.com/console"

# Sheets
SHEET_TITLE = "SRE1_자동화 고객사 목록"

# Threading
MAX_THREAD = 5

# Timeouts (seconds)
IMPLICIT_WAIT = 30
EXPLICIT_WAIT = 10
PAGE_LOAD_TIMEOUT = 30

# Sleep Durations (seconds)
SLEEP_SHORT = 6
SLEEP_MEDIUM = 7
SLEEP_LONG = 8

# CSS Selectors
INTERFERING_SPAN_SELECTOR = "[data-analytics-funnel-key='substep-name']"

# XPaths
XPATHS = {
    "login": {
        "alarm_button": "/html/body/div[2]/div[1]/div/div[3]/div/header/nav/div[1]/div[3]/div[2]/div[1]/div/div/button",
        "all_events_button": "/html/body/div[2]/div[1]/div/div[3]/div/header/nav/div[1]/div[3]/div[2]/div[1]/div/div/div/div/footer/div[1]/a",
    },
    "events_page": {
        "unresolved": {
            "count": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[1]/div/div/div[3]/div[1]/div[1]/div[2]/div/div[1]/div/ul/li[1]/div/a/span/span/span/span",
            "button": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[1]/div/div/div[3]/div[1]/div[1]/div[2]/div/div[1]/div/ul/li[1]/div/a",
        },
        "scheduled": {
            "count": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[1]/div/div/div[3]/div[1]/div[1]/div[2]/div/div[1]/div/ul/li[2]/div/a/span/span/span/span",
            "button": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[1]/div/div/div[3]/div[1]/div[1]/div[2]/div/div[1]/div/ul/li[2]/div/a",
        },
        "other": {
            "count": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[1]/div/div/div[3]/div[1]/div[1]/div[2]/div/div[1]/div/ul/li[3]/div/a/span/span/span/span",
            "button": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[1]/div/div/div[3]/div[1]/div[1]/div[2]/div/div[1]/div/ul/li[3]/div/a",
        },
        "tbody": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[1]/div/div/div[3]/div[1]/div[2]/div/div/section/div/div/div[2]/div/div[1]/table/tbody",
        "detail": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[2]/section/div/div[2]/div[2]/div/div/div/div/div/div/div[2]/div[1]/div/div/div[2]/div",
        "cancel_button": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[2]/section/div/div[2]/div[1]/div/div/button[2]",
    },
    "affected_resources": {
        "tab": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[2]/section/div/div[2]/div[2]/div/div/div/div/div/div/div[1]/div/ul/li[2]/div/button",
        "link": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[2]/section/div/div[2]/div[2]/div/div/div/div/div/div/div[2]/div[2]/div/section/div/div/div[2]/div/div[1]/table/tbody/tr/td[1]/div/a",
        "text": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[2]/section/div/div[2]/div[2]/div/div/div/div/div/div/div[2]/div[2]/div/section/div/div/div[2]/div/div[1]/table/tbody/tr/td[1]/div/span",
        "next_button": "/html/body/div[2]/div[2]/div/div[1]/div/div/div/div/main/div[2]/section/div/div[2]/div[2]/div/div/div/div/div/div/div[2]/div[2]/div/section/div/div/div[1]/div/div/div[2]/div[2]/div/ul/li[4]/button",
    },
}

# Key mapping for event details
KEY_MAPPING = {
    "서비스": "Service",
    "시작 시간": "Start time",
    "상태": "Status",
    "종료 시간": "End time",
    "리전/가용 영역": "Region / Availability Zone",
    "범주": "Category",
    "계정별": "Account specific",
    "영향을 받는 리소스": "Affected resources",
    "설명": "Description",
}



########## sheets_auth_selector.py ##########
########## sheets_auth_selector.py ##########
########## sheets_auth_selector.py ##########

# Google Sheets
GOOGLE_CREDENTIALS_FILE = "total-pad-452908-i9-262988efc1a1.json"
GSHEET_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
SHEET_RANGE = "A6:AC6"

# Missing clients logger
MISSING_CLIENTS_LOG_FILE = "missing_clients.log"
MISSING_CLIENTS_LOGGER_NAME = "missing_clients"
MISSING_CLIENTS_LOG_LEVEL = logging.INFO
MISSING_CLIENTS_LOG_FORMAT = "%(asctime)s - %(message)s"
MISSING_CLIENTS_LOG_MODE = "w"

# Exclusion keywords
EXCLUDE_KEYWORDS = ["issuereporter", "NCP"]


########## events_extractor.py ##########
########## events_extractor.py ##########
########## events_extractor.py ##########

WEB_SERVER_URL = "http://127.0.0.1:4000/api/events"
