# src/utils/baml_helper.py

from typing import Any, AsyncGenerator, Union, Protocol
from src.agent.shared.types import StreamChunk, ChunkType


# 定義一個 Protocol，確保傳進來的 partial 物件都有 decision 屬性
# (這是 Python 的 Duck Typing 寫法)
class HasDecision(Protocol):
    @property
    def decision(self) -> Any: ...


async def stream_summary(stream: Any) -> AsyncGenerator[Union[StreamChunk, Any], None]:
    """
    通用函式：將 BAML 的同步串流轉換為 StreamChunk + Final Result 的異步串流。

    Args:
        baml_stream: b.stream.Xxxx() 回傳的串流物件

    Yields:
        StreamChunk: 思考過程
        Any: 最終的 BAML Result 物件
    """
    last_title = ""
    last_desc_len = 0

    # 1. 處理串流過程 (Thought)
    for partial in stream:
        # 防呆：確保有 decision 欄位
        summary = None
        confidence = None

        if hasattr(partial, "decision") and partial.decision:
            summary = getattr(partial.decision, "summary", None)
            confidence = getattr(partial.decision, "confidence", None)
        elif hasattr(partial, "insight") and partial.insight:
            summary = getattr(partial.insight, "summary", None)

        if not summary:
            continue

        title = summary.title or ""
        desc = summary.description or ""

        # 情況 A: title 變更 -> 發送新步驟
        if title and title != last_title:
            last_title = title
            last_desc_len = len(desc)
            if desc.strip():
                yield StreamChunk(
                    type=ChunkType.THOUGHT,
                    content=title,
                    meta={
                        "description": desc,
                        "confidence": confidence,
                    },
                )

        # 情況 B: title 沒變，description 變長 -> 更新詳細內容
        elif len(desc) > last_desc_len:
            yield StreamChunk(
                type=ChunkType.THOUGHT,
                content=title,
                meta={
                    "description": desc,
                    "confidence": confidence,
                },
            )
            last_desc_len = len(desc)

    # 2. 處理最終結果
    # 注意：這裡不需要 await，因為 baml stream 是同步的
    yield stream.get_final_response()
