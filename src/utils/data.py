"""
Data utilities
"""

import re
from typing import Any

from jsonpath_ng.ext import parse as ext_parse


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


def extract_value(data: Any, path: str) -> Any:
    """
    使用 jsonpath-ng 從 JSON 資料中提取值
    支援高級過濾語法，例如: data.records[?(@.name=='研發部')].id
    """
    if not path:
        return None

    try:
        # 1. 嘗試直接解析
        jsonpath_expr = ext_parse(path)
        matches = jsonpath_expr.find(data)

        # 2. 容錯處理：如果沒找到，且路徑以 "data." 開頭
        # 有時候 LLM 會以為根節點叫 data，但其實傳進來的 dict 本身就是 data
        if not matches and path.startswith("data."):
            try:
                # 去掉 "data." 再試一次
                alt_path = path[5:]
                alt_expr = ext_parse(alt_path)
                matches = alt_expr.find(data)
            except:
                pass

        if matches:
            # 通常我們只需要第一個符合的結果
            return matches[0].value

        return None

    except Exception as e:
        print(f"⚠️ JSONPath Parsing Error: {e} | Path: {path}")
        return None
