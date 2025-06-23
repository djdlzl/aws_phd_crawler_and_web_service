# config.py
import os

# Database configuration
BASE_DIR = os.path.dirname(__file__)
DB_FILENAME = "aws_events.db"
DB_PATH = os.path.join(BASE_DIR, DB_FILENAME)

# Flask application
APP_HOST = "0.0.0.0"
APP_PORT = 4000

# Date/time format
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

