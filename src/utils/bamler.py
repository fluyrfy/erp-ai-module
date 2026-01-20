# src/utils/baml_helper.py

from typing import Any, AsyncGenerator, Union, Protocol
from src.agent.shared.types import StreamChunk, ChunkType


# 定義一個 Protocol，確保傳進來的 partial 物件都有 decision 屬性
# (這是 Python 的 Duck Typing 寫法)
class HasDecision(Protocol):
    @property
    def decision(self) -> Any: ...


async def stream_decision(stream: Any) -> AsyncGenerator[Union[StreamChunk, Any], None]:
    """
    通用函式：將 BAML 的同步串流轉換為 StreamChunk + Final Result 的異步串流。

    Args:
        baml_stream: b.stream.Xxxx() 回傳的串流物件

    Yields:
        StreamChunk: 思考過程
        Any: 最終的 BAML Result 物件
    """
    last_action = ""
    last_reason_len = 0

    # 1. 處理串流過程 (Thought)
    for partial in stream:
        # 防呆：確保有 decision 欄位
        if not hasattr(partial, "decision") or not partial.decision:
            continue

        current_action = partial.decision.action or ""
        current_reason = partial.decision.reason or ""

        # 情況 A: Action 變更 -> 發送新步驟
        if current_action and current_action != last_action:
            last_action = current_action
            last_reason_len = len(current_reason)
            if current_reason.strip():
                yield StreamChunk(
                    type=ChunkType.THOUGHT,
                    content=current_action,
                    meta={
                        "reason": current_reason,
                        "confidence": partial.decision.confidence,
                    },
                )

        # 情況 B: Action 沒變，Reason 變長 -> 更新詳細內容
        elif len(current_reason) > last_reason_len:
            yield StreamChunk(
                type=ChunkType.THOUGHT,
                content=current_action,
                meta={
                    "reason": current_reason,
                    "confidence": partial.decision.confidence,
                },
            )
            last_reason_len = len(current_reason)

    # 2. 處理最終結果
    # 注意：這裡不需要 await，因為 baml stream 是同步的
    final_result = stream.get_final_response()
    yield final_result
