import logging
from typing import Any

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from gradio import Server

from config import validate_config

from .chat import router as chat_router
from .settings import ALLOWED_ORIGINS

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger("meninas_digitais.api")

app = Server(
    title="Assistente Meninas Digitais",
    description="API do assistente GraphRAG sobre os artigos do WIT.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

app.include_router(chat_router)


@app.get("/api/health")
def health() -> Any:
    """Healthcheck sem chamadas ao Neo4j/LLM (rápido e barato)."""
    try:
        validate_config()
    except RuntimeError as exc:
        logger.warning("Configuração incompleta: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "service": "meninas-digitais-api",
                "detail": str(exc),
            },
        )
    return {
        "status": "ok",
        "service": "meninas-digitais-api",
        "version": 1,
    }


@app.get("/api")
def api_info() -> dict[str, Any]:
    return {
        "service": "Assistente Meninas Digitais",
        "version": 1,
        "endpoints": {
            "chat": "POST /api/chat (text/event-stream)",
            "health": "GET /api/health",
            "docs": "GET /api/docs",
        },
    }
