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
    HTTP_TIMEOUT = 30.0

    # Output Formatting
    JSON_INDENT = 2  # 設定 JSON 縮排，預設為 2，設為 0 或 None 則為 minified json
    RECORD_LIMIT_SAFE = 100  # 安全區：全部給 LLM
    RECORD_LIMIT_TRUNCATE = 200  # 警戒區：截斷


config = Config()
