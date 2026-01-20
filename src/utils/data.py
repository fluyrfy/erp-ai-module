"""
Data utilities
"""

from collections import Counter
import re
from typing import Any, Dict, List

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


def aggregate_records(
    records: List[Dict[str, Any]],
    target_field: str,
) -> List[Dict[str, Any]]:
    """
    Output type: list[dict[str, Any]]
    回傳 bucket records，讓上層沿用同一套 records truncate。
    """
    if not records or not target_field:
        return records

    values = [str(r.get(target_field, "Unknown")) for r in records]
    counts = Counter(values)

    # count desc
    items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)

    return [
        {"_group_field": target_field, "_group_value": k, "_count": v} for k, v in items
    ]


def sort_records(
    records: List[Dict[str, Any]],
    sort_field: str,
    order: str = "ASC",
) -> List[Dict[str, Any]]:
    """
    Output type: list[dict[str, Any]]
    """
    if not records or not sort_field:
        return records

    order = (order or "ASC").upper()
    reverse = order == "DESC"

    def sort_key(r: Dict[str, Any]):
        v = r.get(sort_field, None)

        # None / 空字串：統一排最後（不論 ASC/DESC）
        if v is None or v == "":
            return (1, "")

        # number
        if isinstance(v, (int, float)):
            return (0, float(v))

        # numeric string -> float
        if isinstance(v, str):
            s = v.strip()
            try:
                return (0, float(s))
            except Exception:
                return (0, s.lower())

        # fallback
        return (0, str(v).lower())

    return sorted(records, key=sort_key, reverse=reverse)
