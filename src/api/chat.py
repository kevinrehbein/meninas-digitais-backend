"""Endpoint de chat com streaming Server-Sent Events."""

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sse_starlette import EventSourceResponse

from config import MAX_QUESTION_CHARS

from .service import run_graph
from .settings import (
    CONTRACT_VERSION,
    MAX_CONCURRENT_RUNS,
    MAX_STREAM_SECONDS,
    SSE_HEARTBEAT_SECONDS,
)

logger = logging.getLogger("meninas_digitais.api.chat")
router = APIRouter(prefix="/api", tags=["chat"])
_runs = asyncio.Semaphore(MAX_CONCURRENT_RUNS)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_CHARS)

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


def _event(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {
        "event": event,
        "data": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    }


@router.post("/chat")
async def chat(payload: ChatRequest) -> EventSourceResponse:
    request_id = uuid4().hex

    def error(code: str, message: str) -> dict[str, str]:
        return _event("error", {
            "code": code, "message": message,
            "retryable": True, "request_id": request_id,
        })

    async def stream():
        yield _event("meta", {"version": CONTRACT_VERSION, "request_id": request_id})
        try:
            async with _runs, asyncio.timeout(MAX_STREAM_SECONDS):
                async for item in run_graph(payload.question):
                    yield _event(item["event"], item["data"])
        except TimeoutError:
            yield error("timeout", "A resposta demorou mais que o esperado. Tente reformular a pergunta.")
        except Exception:
            logger.exception("Falha ao executar o grafo (request_id=%s)", request_id)
            yield error("internal_error", "Não foi possível concluir a resposta agora. Tente novamente em instantes.")

    return EventSourceResponse(
        stream(),
        ping=SSE_HEARTBEAT_SECONDS,
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )