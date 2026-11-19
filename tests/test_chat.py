import asyncio
import json

import pytest
from pydantic import ValidationError

from api import chat


def decode_sse(chunks):
    decoded = []
    event = None

    for chunk in chunks:
        if isinstance(chunk, dict):
            data = chunk["data"]

            decoded.append(
                (
                    chunk["event"],
                    json.loads(data) if isinstance(data, str) else data,
                )
            )
            continue

        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")

        for line in chunk.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()

            elif line.startswith("data:"):
                data = line.removeprefix("data:").strip()
                decoded.append((event, json.loads(data)))

    return decoded


@pytest.mark.parametrize("question", ["", "   ", "\n\t "])
def test_chat_request_rejects_empty_or_whitespace_question(question):
    with pytest.raises(ValidationError):
        chat.ChatRequest(question=question)


def test_chat_request_strips_question():
    assert chat.ChatRequest(question="  pergunta  ").question == "pergunta"


def test_chat_request_rejects_question_over_limit():
    from config import MAX_QUESTION_CHARS

    with pytest.raises(ValidationError):
        chat.ChatRequest(question="x" * (MAX_QUESTION_CHARS + 1))


def test_event_serializes_unicode_and_compact_json():
    result = chat._event("status", {"texto": "ação", "n": 1})
    assert result["event"] == "status"
    assert json.loads(result["data"]) == {"texto": "ação", "n": 1}
    assert "\\u00e7" not in result["data"]


@pytest.mark.asyncio
async def test_chat_streams_meta_and_graph_events(monkeypatch):
    async def fake_run_graph(question):
        assert question == "pergunta"
        yield {"event": "status", "data": {"node": "supervisor"}}
        yield {"event": "final", "data": {"answer_markdown": "ok"}}

    monkeypatch.setattr(chat, "run_graph", fake_run_graph)
    monkeypatch.setattr(chat, "_runs", asyncio.Semaphore(1))
    response = await chat.chat(chat.ChatRequest(question="pergunta"))
    events = decode_sse([chunk async for chunk in response.body_iterator])

    assert [event for event, _ in events] == ["meta", "status", "final"]
    assert events[0][1]["version"] == chat.CONTRACT_VERSION
    assert events[0][1]["request_id"]


@pytest.mark.asyncio
async def test_chat_converts_unexpected_exception_to_safe_error(monkeypatch):
    async def failing_graph(question):
        raise RuntimeError("segredo interno")
        yield  # pragma: no cover

    monkeypatch.setattr(chat, "run_graph", failing_graph)
    monkeypatch.setattr(chat, "_runs", asyncio.Semaphore(1))
    response = await chat.chat(chat.ChatRequest(question="pergunta"))
    events = decode_sse([chunk async for chunk in response.body_iterator])

    assert [event for event, _ in events] == ["meta", "error"]
    error = events[-1][1]
    assert error["code"] == "internal_error"
    assert "segredo interno" not in error["message"]
    assert error["retryable"] is True
    assert error["request_id"] == events[0][1]["request_id"]


@pytest.mark.asyncio
async def test_chat_converts_timeout_to_timeout_error(monkeypatch):
    async def slow_graph(question):
        await asyncio.sleep(0.02)
        yield {"event": "final", "data": {}}

    monkeypatch.setattr(chat, "run_graph", slow_graph)
    monkeypatch.setattr(chat, "_runs", asyncio.Semaphore(1))
    monkeypatch.setattr(chat, "MAX_STREAM_SECONDS", 0.001)
    response = await chat.chat(chat.ChatRequest(question="pergunta"))
    events = decode_sse([chunk async for chunk in response.body_iterator])

    assert [event for event, _ in events] == ["meta", "error"]
    assert events[-1][1]["code"] == "timeout"


@pytest.mark.asyncio
async def test_each_chat_request_gets_a_distinct_request_id(monkeypatch):
    async def empty_graph(question):
        if False:
            yield {}

    monkeypatch.setattr(chat, "run_graph", empty_graph)
    monkeypatch.setattr(chat, "_runs", asyncio.Semaphore(1))
    ids = []
    for _ in range(2):
        response = await chat.chat(chat.ChatRequest(question="pergunta"))
        events = decode_sse([chunk async for chunk in response.body_iterator])
        ids.append(events[0][1]["request_id"])
    assert ids[0] != ids[1]
