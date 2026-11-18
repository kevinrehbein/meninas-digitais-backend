"""Endpoint de chat com streaming Server-Sent Events."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from config import MAX_QUESTION_CHARS

from .service import get_service
from .settings import (
    CONTRACT_VERSION,
    MAX_STREAM_SECONDS,
    RATE_LIMIT_PER_MINUTE,
    SSE_HEARTBEAT_SECONDS,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger("meninas_digitais.api.chat")

router = APIRouter(prefix="/api", tags=["chat"])

_hits: dict[str, deque[float]] = defaultdict(deque)
_RATE_WINDOW_SECONDS = 60.0


class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=MAX_QUESTION_CHARS,
        description="Pergunta do usuário sobre a base do WIT.",
    )

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


def _sse(event: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    host = request.client.host if request.client else "unknown"
    return forwarded.split(",")[0].strip() or host


def _check_rate_limit(key: str) -> bool:
    if RATE_LIMIT_PER_MINUTE <= 0:
        return True
    now = time.monotonic()
    bucket = _hits[key]
    while bucket and now - bucket[0] > _RATE_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        return False
    bucket.append(now)
    return True


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Responde com Server-Sent Events: meta, status, final ou error."""
    if not _check_rate_limit(_client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Muitas perguntas em pouco tempo. "
                "Aguarde um instante e tente novamente."
            ),
        )

    request_id = uuid4().hex
    service = get_service()

    async def event_stream() -> AsyncIterator[bytes]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        stop_event = threading.Event()

        def emit(item: dict[str, Any] | None) -> None:
            # O event loop já pode ter sido encerrado (cliente desconectou).
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(queue.put_nowait, item)

        def producer() -> None:
            try:
                for item in service.stream(payload.question, stop_event):
                    if stop_event.is_set():
                        break
                    emit(item)
            except Exception:
                logger.exception(
                    "Falha ao executar o grafo (request_id=%s)", request_id
                )
                emit(
                    {
                        "event": "error",
                        "data": {
                            "code": "internal_error",
                            "message": (
                                "Não foi possível concluir a resposta agora. "
                                "Tente novamente em instantes."
                            ),
                            "retryable": True,
                            "request_id": request_id,
                        },
                    }
                )
            finally:
                emit(None)

        thread = threading.Thread(
            target=producer,
            name=f"chat-{request_id[:8]}",
            daemon=True,
        )
        thread.start()

        started = time.monotonic()
        yield _sse(
            "meta",
            {
                "version": CONTRACT_VERSION,
                "request_id": request_id,
            },
        )

        try:
            while True:
                if time.monotonic() - started > MAX_STREAM_SECONDS:
                    stop_event.set()
                    yield _sse(
                        "error",
                        {
                            "code": "timeout",
                            "message": (
                                "A resposta demorou mais que o esperado. "
                                "Tente reformular a pergunta."
                            ),
                            "retryable": True,
                            "request_id": request_id,
                        },
                    )
                    break

                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=SSE_HEARTBEAT_SECONDS
                    )
                except TimeoutError:
                    if await request.is_disconnected():
                        stop_event.set()
                        break
                    yield b": keep-alive\n\n"
                    continue

                if item is None:
                    break

                if await request.is_disconnected():
                    stop_event.set()
                    break

                yield _sse(item["event"], item["data"])
        finally:
            stop_event.set()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
