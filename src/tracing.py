"""
Query & Result 記錄
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

TRACE_DIR = Path("logs/traces")
TRACE_DIR.mkdir(parents=True, exist_ok=True)


def save_trace(
    module: str,
    user_query: str,
    success: bool,
    result: str = None,
    error: str = None,
    duration_ms: float = None,
    raw_response: dict = None,
    **metadata,
):
    """儲存一筆 query & result"""
    record = {
        "trace_id": f"tr_{uuid.uuid4().hex[:12]}",
        "timestamp": datetime.now().isoformat(),
        "module": module,
        "user_query": user_query,
        "success": success,
        "result": result[:1000] if result else None,
        "error": error,
        "duration_ms": round(duration_ms, 2) if duration_ms else None,
        "raw_response": raw_response,
        "metadata": metadata,
    }

    file_path = TRACE_DIR / f"{datetime.now().date()}.jsonl"
    with open(file_path, "a", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)
        f.write("\n")
