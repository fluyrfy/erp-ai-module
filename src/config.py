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

    # Agent Settings
    DEFAULT_LANGUAGE = "Traditional Chinese"
    CONFIDENCE_THRESHOLD = 0.5
    HTTP_TIMEOUT = 30.0


config = Config()
