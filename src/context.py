# src/context.py
from contextvars import ContextVar

# 定義全域 context
request_token: ContextVar[str | None] = ContextVar("request_token", default=None)
