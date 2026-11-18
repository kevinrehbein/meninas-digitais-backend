"""Execução do grafo de agentes com eventos prontos para streaming."""

import logging
import time
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from agents.graph import graph_builder
from agents.state import initial_state
from agents.utils import format_final_response
from config import GRAPH_RECURSION_LIMIT, validate_config

from .progress import describe_update
from .settings import MAX_SOURCES
from .sources import extract_sources

logger = logging.getLogger("meninas_digitais.api.service")


@lru_cache(maxsize=1)
def get_graph() -> Any:
    validate_config()
    logger.info("Compilando grafo de agentes")
    return graph_builder()


async def run_graph(question: str) -> AsyncIterator[dict[str, Any]]:
    started = time.perf_counter()
    final: dict[str, Any] = {}
    sources: dict[str, dict[str, str]] = {}

    async for chunk in get_graph().astream(
        initial_state(question),
        config={"recursion_limit": GRAPH_RECURSION_LIMIT},
        stream_mode="updates",
    ):
        for node, update in chunk.items():
            if not isinstance(update, dict):
                continue
            if node == "pesquisador_tools":
                for url, src in extract_sources(update.get("messages") or []).items():
                    sources.setdefault(url, src)
            final.update({k: v for k, v in update.items() if k != "messages"})
            yield {"event": "status", "data": describe_update(node, update)}

    response = final.get("final_response")
    is_plan = isinstance(response, dict)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("Resposta em %dms | intent=%s | fontes=%d",
                elapsed_ms, final.get("intent"), len(sources))

    yield {
        "event": "final",
        "data": {
            "answer_markdown": format_final_response(response),
            "warning": final.get("warning"),
            "response_type": "plan" if is_plan else "text",
            "plan": response if is_plan else None,
            "sources": list(sources.values())[:MAX_SOURCES],
            "meta": {
                "intent": final.get("intent"),
                "complexity": final.get("complexity"),
                "verdict": final.get("verdict"),
                "iterations": final.get("iteration_count", 0),
                "elapsed_ms": elapsed_ms,
            },
        },
    }