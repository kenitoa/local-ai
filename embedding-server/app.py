"""local-ai embedding-server (Step 8: \uc784\ubca0\ub529 \uc0dd\uc131 stub)."""
import hashlib
import logging
import math
import os
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel

SERVICE_NAME = os.getenv("SERVICE_NAME", "embedding-server")
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f"{SERVICE_NAME}.log")),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(SERVICE_NAME)

app = FastAPI(title=f"local-ai {SERVICE_NAME}")


@app.get("/")
def root():
    return {"service": SERVICE_NAME, "status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("startup")
def _startup():
    log.info("%s service started", SERVICE_NAME)


# ---------------------------------------------------------------------------
# Step 8: /api/v1/embed - \uc784\ubca0\ub529 \ubca1\ud130 \uc0dd\uc131 stub
# \uc2e4\uc81c \ubaa8\ub378 \uc5c6\uc774 \ud574\uc2dc \uae30\ubc18 \uacb0\uc815\uc801 \uac00\uc9dc-\uc784\ubca0\ub529\uc744 \uc0dd\uc131\ud55c\ub2e4. \ub2e4\uc6b4\uc2a4\ud2b8\ub9bc\uc740 \ub3d9\uc77c \uc785\ub825 = \ub3d9\uc77c \ubca1\ud130\ub97c \uae30\ub300\ud558\ubbc0\ub85c
# \uc720\uc0ac\ub3c4 \ud14c\uc2a4\ud2b8\uc5d0 \ucda9\ubd84\ud558\ub2e4.
# ---------------------------------------------------------------------------
class EmbedIn(BaseModel):
    text: str
    model: str | None = None
    dim: int | None = 128


DEFAULT_MODEL = os.getenv("DEFAULT_EMBEDDING_MODEL", "stub-hash")


def _hash_embedding(text: str, dim: int) -> list[float]:
    """\ud574\uc2dc \uae30\ubc18 \uc7ac\ud604 \uac00\ub2a5\ud55c \ubca1\ud130. L2 \ub178\ub984\uc73c\ub85c \uc815\uaddc\ud654."""
    vec = [0.0] * dim
    if not text:
        return vec
    chunks = max(1, (len(text.encode("utf-8")) // 32) + 1)
    data = text.encode("utf-8")
    for i in range(chunks):
        h = hashlib.sha256(str(i).encode() + data).digest()
        for j, b in enumerate(h):
            vec[(i * len(h) + j) % dim] += (b - 128) / 128.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


@app.post("/api/v1/embed")
def embed(payload: EmbedIn):
    dim = max(8, min(payload.dim or 128, 1024))
    vec = _hash_embedding(payload.text or "", dim)
    sha = hashlib.sha256((payload.text or "").encode("utf-8")).hexdigest()
    return {
        "model": payload.model or DEFAULT_MODEL,
        "dim": dim,
        "vector": vec,
        "content_hash": sha,
        "stub": True,
    }
