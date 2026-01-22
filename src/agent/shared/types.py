# src/agent/shared/types.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

from baml_client.types import DecisionMetadata
from src.agent.shared.errors import AgentException, ErrorCode


class ChunkType(str, Enum):
    # 思考過程 (例如: "正在分析薪資資料...")
    THOUGHT = "thought"

    # 正式回答 (例如: "研發處的薪資為...")
    ANSWER = "answer"


class StreamChunk(BaseModel):
    """串流中的文字片段"""

    type: ChunkType
    content: str
    meta: Optional[dict[str, Any]] = None

    @classmethod
    def thought(cls, source_obj: Any, content: str = None):
        """
        自動從 BAML 物件 (Task, ApiChoice...) 提取 decision 並轉成 StreamChunk。

        Args:
            source_obj: 包含 decision 屬性的物件 (例如 ApiChoice)
            content: (選填) 如果想覆蓋預設的 summary title 文字，可傳入此參數。
                     例如傳入 "POST /api/search" 覆蓋原本的 action。
        """
        # 安全取得 decision (防呆)
        decision: DecisionMetadata = getattr(source_obj, "decision", None)

        # 1. 決定 Content (優先用傳入的 override，沒有就用 decision.summary.title，再沒有就顯示未知)
        final_content = content or (
            decision.summary.title if decision else "Processing"
        )

        # 2. 決定 Reason & Confidence
        description = decision.summary.description if decision else ""
        confidence = getattr(decision, "confidence", None) if decision else None

        return cls(
            type=ChunkType.THOUGHT,
            content=final_content,
            meta={"description": description, "confidence": confidence},
        )


@dataclass
class StreamDone:
    """串流結束，帶完整結果"""

    result: Any  # 可以是 Briefing、dict、或其他
    error: str | None = None


StreamEvent = StreamChunk | StreamDone


class AgentError(BaseModel):
    """最終輸出的錯誤結構 (不可變數據)"""

    code: ErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_exception(cls, e: AgentException) -> "AgentError":
        return cls(code=e.code, message=e.message, details=e.details)

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }


class AgentResult(BaseModel):
    """Agent 的最終回傳結果 (Success or Fail)"""

    success: bool
    data: Any = None
    error: Optional[AgentError] = None

    @classmethod
    def ok(cls, data: Any) -> "AgentResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: AgentError) -> "AgentResult":
        return cls(success=False, error=error)
