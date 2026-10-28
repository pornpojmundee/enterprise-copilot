"""Text embeddings.

Default: BAAI/bge-m3 running locally (free, multilingual incl. Thai, 1024-dim).
The first run downloads the model (~2.3 GB) into the Hugging Face cache.

EMBEDDING_BACKEND=hash gives a tiny deterministic fake embedder for unit tests / CI
where the model can't be downloaded. It is NOT semantic — never use it for real answers.
"""
from __future__ import annotations

import hashlib
import math
import os
from functools import lru_cache
from typing import Protocol

DIM = 1024


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # heavy import, only when used

        self.name = model_name
        self._model = SentenceTransformer(model_name)
        dim = self._model.get_sentence_embedding_dimension()
        if dim != DIM:
            raise ValueError(f"{model_name} has dim {dim}; kb.chunks.embedding is vector({DIM})")

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=len(texts) > 32)
        return [v.tolist() for v in vecs]


class HashEmbedder:
    """Bag-of-tokens hashed into DIM buckets, L2-normalized. Test-only."""

    name = "hash-test"

    def embed(self, texts: list[str]) -> list[list[float]]:
        from .text import tokenize

        out = []
        for t in texts:
            v = [0.0] * DIM
            for tok in tokenize(t):
                h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "little")
                v[h % DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    backend = os.getenv("EMBEDDING_BACKEND", "local").lower()
    if backend == "hash":
        return HashEmbedder()
    return LocalEmbedder(os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"))
