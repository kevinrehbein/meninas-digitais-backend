"""Execução do grafo de agentes com eventos prontos para streaming."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

from agents.graph import graph_builder
from agents.state import initial_state
from agents.utils import format_final_response
from config import GRAPH_RECURSION_LIMIT, validate_config

from .progress import describe_update
from .settings import MAX_CONCURRENT_RUNS, MAX_SOURCES
from .sources import extract_sources

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger("meninas_digitais.api.service")


class ChatService:
    """Compila o grafo uma única vez por instância morna da função."""

    def __init__(self) -> None:
        self._graph: Any = None
        self._lock = threading.Lock()
        self._runs = threading.BoundedSemaphore(MAX_CONCURRENT_RUNS)

    def _get_graph(self) -> Any:
        if self._graph is None:
            with self._lock:
                if self._graph is None:
                    validate_config()
                    self._graph = graph_builder()
                    logger.info("Grafo de agentes compilado")
        return self._graph

    def stream(
        self,
        question: str,
        stop_event: threading.Event,
    ) -> Iterator[dict[str, Any]]:
        """Gera eventos `status` e, ao final, um evento `final`.

        A execução do LangGraph é síncrona. O router consome este iterador em
        uma thread separada para conseguir enviar heartbeats enquanto o modelo
        ou o Neo4j estão trabalhando.
        """
        started = time.perf_counter()
        graph = self._get_graph()
        final: dict[str, Any] = {}
        sources: dict[str, dict[str, str]] = {}

        with self._runs:
            for chunk in graph.stream(
                initial_state(question),
                config={"recursion_limit": GRAPH_RECURSION_LIMIT},
                stream_mode="updates",
            ):
                if stop_event.is_set():
                    logger.info("Execução cancelada pelo cliente")
                    return

                for node, update in chunk.items():
                    if not isinstance(update, dict):
                        continue

                    if node == "pesquisador_tools":
                        found = extract_sources(update.get("messages") or [])
                        for url, source in found.items():
                            sources.setdefault(url, source)

                    final.update(
                        {
                            key: value
                            for key, value in update.items()
                            if key != "messages"
                        }
                    )
                    yield {
                        "event": "status",
                        "data": describe_update(node, update),
                    }

        response = final.get("final_response")
        answer = format_final_response(response)
        source_list = list(sources.values())[:MAX_SOURCES]
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        logger.info(
            "Resposta concluída em %dms | intent=%s | fontes=%d",
            elapsed_ms,
            final.get("intent"),
            len(source_list),
        )

        yield {
            "event": "final",
            "data": {
                "answer_markdown": answer,
                "warning": final.get("warning"),
                "response_type": "plan" if isinstance(response, dict) else "text",
                "plan": response if isinstance(response, dict) else None,
                "sources": source_list,
                "meta": {
                    "intent": final.get("intent"),
                    "complexity": final.get("complexity"),
                    "verdict": final.get("verdict"),
                    "iterations": final.get("iteration_count", 0),
                    "elapsed_ms": elapsed_ms,
                },
            },
        }


_service: ChatService | None = None
_service_lock = threading.Lock()


def get_service() -> ChatService:
    global _service  # noqa: PLW0603
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = ChatService()
    return _service
