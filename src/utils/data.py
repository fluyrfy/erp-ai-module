"""
Data utilities
"""

import re
from typing import Any


def get_nested(data: Any, path: str) -> Any:
    """
    取 nested 值

    支援格式:
    - "data[0].id"
    - "items[0].name"
    - "result.total"
    - "data[0].children[1].id"

    Args:
        data: 原始資料（dict 或 list）
        path: 欄位路徑

    Returns:
        取得的值

    Raises:
        KeyError: 找不到欄位
        IndexError: 索引超出範圍
    """
    current = data

    for part in re.split(r"\.|\[|\]", path):
        if not part:
            continue
        if part.isdigit():
            current = current[int(part)]
        else:
            current = current[part]

    return current
