"""
Configuration management
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # LLM
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # Backend Service
    BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8080")
    BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")
    SWAGGER_DOC_PATH = "/v3/api-docs"

    # Agent Settings
    DEFAULT_LANGUAGE = "Traditional Chinese"
    CONFIDENCE_THRESHOLD = 0.6

    # HTTP
    HTTP_TIMEOUT_S = 30.0
    HTTP_RETRIES = 0
    HTTP_RETRY_BACKOFF_S = 0.3

    # Output Formatting
    JSON_INDENT = 2  # 設定 JSON 縮排，預設為 2，設為 0 或 None 則為 minified json
    RECORD_LIMIT_SAFE = 100  # 安全區：全部給 LLM
    RECORD_LIMIT_TRUNCATE = 200  # 警戒區：截斷


config = Config()
