import json
import os
import threading
import time

from dotenv import load_dotenv
from gradio_client import Client
from langchain_core.embeddings import Embeddings

DIM = 1024

load_dotenv()

class SpaceEmbeddings(Embeddings):
    """Embeddings BGE-M3 servidos por um Space do Hugging Face (Gradio)."""

    def __init__(self, space_id: str, retries: int = 8, wait: float = 20.0, batch_size: int = 16) -> None:
        self.space_id = space_id
        self.retries = retries
        self.wait = wait
        self.batch_size = batch_size
        self._client: Client | None = None
        self._lock = threading.Lock()

    def _get_client(self) -> Client:
        with self._lock:
            if self._client is None:
                self._client = Client(
                    self.space_id, verbose=False, httpx_kwargs={"timeout": 60}
                )
            return self._client

    def _call(self, texts: list[str]) -> list[list[float]]:
        # Space dormindo leva alguns minutos para acordar: tenta várias vezes.
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._get_client().predict(json.dumps(texts), api_name="/embed")
            except Exception as exc:
                last = exc
                self._client = None
                time.sleep(self.wait)
        raise RuntimeError(f"Space de embeddings indisponível: {last}")

    def embed_query(self, text: str) -> list[float]:
        return self._call([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out.extend(self._call(texts[i : i + self.batch_size]))
        return out

def get_embeddings() -> Embeddings:
    space_id = os.getenv("EMBEDDING_SPACE")
    if not space_id:
        raise RuntimeError("Defina EMBEDDING_SPACE no .env")
    return SpaceEmbeddings(space_id)