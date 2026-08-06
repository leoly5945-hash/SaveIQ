"""Pure-Python user embeddings from click/category history (Gate 8 v0)."""

from __future__ import annotations

import hashlib
import math

EMBEDDING_DIM = 8
MAX_CLICK_HISTORY = 50


def empty_embedding() -> list[float]:
    return [0.0] * EMBEDDING_DIM


def compute_user_embedding(
    *,
    click_history: list[int],
    preferred_categories: list[str],
) -> list[float]:
    """
    Deterministic hashing embedding (no numpy / surprise).

    Offer IDs and category strings are hashed into a fixed bucket vector and L2-normalized.
    Math collaborators may replace this with SVD / MF later without changing the API.
    """
    vector = empty_embedding()
    for offer_id in click_history[-MAX_CLICK_HISTORY:]:
        _accumulate(vector, f"offer:{offer_id}", weight=1.0)
    for index, category in enumerate(preferred_categories[:12]):
        weight = 1.0 / (1.0 + index)
        _accumulate(vector, f"cat:{category.strip().lower()}", weight=weight)
    return _l2_normalize(vector)


def _accumulate(vector: list[float], token: str, *, weight: float) -> None:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    for i in range(EMBEDDING_DIM):
        # Map two bytes to signed contribution in [-1, 1].
        raw = digest[i * 2] + digest[i * 2 + 1] * 256
        signed = (raw / 65535.0) * 2.0 - 1.0
        vector[i] += signed * weight


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm < 1e-9:
        return empty_embedding()
    return [value / norm for value in vector]
