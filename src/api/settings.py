import os

# O frontend chama /api no mesmo domínio (Vercel Services / rewrite local), então
# CORS só é necessário para desenvolvimento fora do proxy do Next.js.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

SSE_HEARTBEAT_SECONDS = max(5.0, float(os.getenv("SSE_HEARTBEAT_SECONDS", "12")))
MAX_CONCURRENT_RUNS = max(1, int(os.getenv("MAX_CONCURRENT_RUNS", "2")))
MAX_STREAM_SECONDS = max(30, int(os.getenv("MAX_STREAM_SECONDS", "280")))
MAX_SOURCES = max(1, int(os.getenv("MAX_SOURCES", "20")))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
CONTRACT_VERSION = 1
