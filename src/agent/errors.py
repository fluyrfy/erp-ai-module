# Error class
"""
Standardized error definitions for L3 Agent
"""
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


# ==========================================
# 1. Error Codes (唯一區分業務邏輯的地方)
# ==========================================
class ErrorCode(Enum):
    # --- Planning Layer (Step 1) ---
    PLAN_NO_API_MATCH = "PLAN_NO_API_MATCH"  # 找不到適合的 API
    PLAN_LOW_CONFIDENCE = "PLAN_LOW_CONFIDENCE"  # 信心不足

    # --- Generation Layer (Step 2) ---
    GEN_INVALID_SCHEMA = "GEN_INVALID_SCHEMA"  # Swagger 解析失敗或參數生成錯誤

    # --- Execution Layer (Step 3) ---
    EXEC_HTTP_ERROR = "EXEC_HTTP_ERROR"  # 4xx, 5xx
    EXEC_TIMEOUT = "EXEC_TIMEOUT"  # 連線逾時

    # --- Data/Logic Layer (Cross-cutting) ---
    DATA_DEPENDENCY_MISSING = "DATA_DEPENDENCY_MISSING"  # 關鍵：依賴斷裂 (Chain Broken)
    DATA_PARSING_FAILED = "DATA_PARSING_FAILED"  # JSONPath 取值失敗

    # --- System ---
    UNKNOWN_ERROR = "UNKNOWN_ERROR"  # 非預期的程式崩潰


# ==========================================
# 2. Control Exception (給 Python 內部流程控制用)
# ==========================================
class AgentException(Exception):
    """
    通用 Agent 異常基類。
    繼承自 Exception，用於中斷當前函式並向上回報預期內的錯誤。
    """

    def __init__(
        self, code: ErrorCode, message: str, details: Optional[dict[str, Any]] = None
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code.value}] {message}")

    def to_response_dict(self) -> dict:
        """
        將異常轉換為「偽造的 API Response」，供 Summary 步驟使用。
        讓 LLM 認為這是一個明確的錯誤回傳，而非幻覺。
        """
        return {
            "status": "error",  # 明確標示狀態
            "code": self.code.value,  # 例如 "DATA_DEPENDENCY_MISSING"
            "message": self.message,  # 人類可讀的錯誤訊息
            "details": self.details,  # 偵錯細節
            "data": {},  # 確保回傳空物件，截斷 LLM 的幻想
        }


# ─────────────── 具體異常實作 (語意化封裝) ───────────────
class DependencyMissingError(AgentException):
    """當前置 API 資料缺失，導致後續步驟無法執行時拋出"""

    def __init__(self, missing_field: str, source_api: str):
        super().__init__(
            code=ErrorCode.DATA_DEPENDENCY_MISSING,
            message=f"Data Chain Broken: Cannot find '{missing_field}' in API '{source_api}'.",
            details={
                "source_api": source_api,
                "missing_field": missing_field,
                "suggestion": "Target data might not exist in the source system.",
            },
        )


# ==========================================
# 3. Transfer Objects (給外部/前端回傳用)
# ==========================================
@dataclass
class AgentError:
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


@dataclass
class AgentResult:
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
