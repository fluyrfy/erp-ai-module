"""
Chat Server - SSE Implementation
=========================================

SSE (Server-Sent Events) based chat API for L2 Agent.

Why SSE instead of WebSocket for single-user chat:
1. Simpler: No connection state management, heartbeat, reconnection logic
2. Standard HTTP: Works with existing auth, load balancers, proxies
3. Stateless: Each request is independent, easier to scale
4. Industry standard: OpenAI, Anthropic, Google all use SSE for chat

Endpoints:
- POST /api/chat          : Chat with streaming response (SSE)
- GET  /api/health        : Health check
- GET  /api/notifications : Background task notifications (SSE) [Future]
"""

import json
import asyncio
from datetime import datetime
from typing import Any, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from baml_client.types import Briefing
from src.agent.l2 import L2Agent
from src.agent.shared.types import AgentResult, ChunkType, StreamChunk, StreamDone

# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════

API_KEY_HEADER = "x-api-key"
VALID_API_KEYS = {"dev-key-123", "test-key-456"}  # TODO: Move to env/database


# ═══════════════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════════════
class ChatRequest(BaseModel):
    """Chat request from client"""

    message: str = Field(
        ..., min_length=1, max_length=10000, description="User's question"
    )
    conversation_id: str | None = Field(
        None, description="Optional conversation ID for context"
    )


class ChatEvent(BaseModel):
    event: str  # SSE 事件名稱: chunk, done, error
    data: dict  # 實際負載資料

    # 幫你把物件轉成 SSE 字串的 Helper Method
    def to_sse_string(self) -> str:
        # ensure_ascii=False 確保中文不會變亂碼
        json_data = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.event}\ndata: {json_data}\n\n"

    # 工廠方法：快速建立 Chunk 事件
    @classmethod
    def chunk(cls, chunk: StreamChunk):
        return cls(event="chunk", data=chunk.model_dump(mode="json"))

    # 工廠方法：快速建立 Done 事件
    @classmethod
    def done(cls, result: Any):
        return cls(event="done", data={"success": True, "result": result})

    # 工廠方法：快速建立 Error 事件
    @classmethod
    def error(cls, message: str):
        return cls(event="error", data={"message": message})


# ═══════════════════════════════════════════════════════════════════
# Agent Integration
# ═══════════════════════════════════════════════════════════════════
async def workflow(message: str, conversation_id: str | None = None):
    try:
        l2_agent = L2Agent()

        async for event in l2_agent.query(message):

            # Case A: 收到 partial（現在 content 是 narrative 的 JSON string）
            if isinstance(event, StreamChunk):
                yield ChatEvent.chunk(event)

            # Case B: 收到結束訊號
            elif isinstance(event, AgentResult):
                if event.success:
                    # 成功：發送 done
                    yield ChatEvent.done(event.data)
                else:
                    #  失敗：發送 error (原本這裡被當成 done 發出去了)
                    yield ChatEvent.error(f"Agent Logic Failed: {event.error.message}")
    except Exception as e:
        yield ChatEvent.error(f"Server Internal Error: {str(e)}")


# ═══════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    print("🚀 ERP AI Chat Server starting...")
    print("📡 SSE endpoint: POST /api/chat")
    yield
    print("👋 ERP AI Chat Server shutting down...")


app = FastAPI(
    title="ERP AI Chat API",
    description="SSE-based chat API for L2 Agent",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0",
    }


@app.post("/api/chat")
async def chat(request: ChatRequest):  # api_key: str = Depends(verify_api_key)
    """
    Chat endpoint with SSE streaming response.
    """

    async def generate_sse():
        # 呼叫邏輯層
        async for chat_event in workflow(request.message, request.conversation_id):

            yield chat_event.to_sse_string()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════════
# Run Server
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
