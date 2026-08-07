"""LLM-backed user embedding with deterministic local fallback (Gate 9)."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Mapping
from typing import Any, Protocol

from app.services.router.providers.openai_compat import (
    JsonHttpTransport,
    UrllibJsonHttpTransport,
)
from app.services.user.embedding import EMBEDDING_DIM, compute_user_embedding, empty_embedding

logger = logging.getLogger(__name__)

QWEN_EMBEDDING_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"


class EmbeddingClient(Protocol):
    def embed(self, text: str, *, timeout_seconds: float) -> list[float]:
        """Return an embedding vector for text."""


class HashFallbackEmbeddingClient:
    """Local deterministic embedding used when LLM embeddings are unavailable."""

    def embed(self, text: str, *, timeout_seconds: float = 1.0) -> list[float]:
        del timeout_seconds
        tokens = [token for token in text.lower().split() if token]
        # Reuse Gate 8 hashing via synthetic click/category inputs.
        click_ids = [int(hashlib.md5(token.encode()).hexdigest()[:6], 16) for token in tokens[:20]]
        return compute_user_embedding(
            click_history=click_ids,
            preferred_categories=tokens[:8],
        )


class QwenEmbeddingClient:
    def __init__(
        self,
        api_key: str | None,
        transport: JsonHttpTransport | None = None,
        *,
        model: str = "text-embedding-v3",
        base_url: str = QWEN_EMBEDDING_URL,
    ) -> None:
        self._api_key = api_key
        self._transport = transport or UrllibJsonHttpTransport()
        self._model = model
        self._base_url = base_url

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def embed(self, text: str, *, timeout_seconds: float) -> list[float]:
        if not self._api_key:
            raise RuntimeError("Qwen embedding client is not configured")
        response = self._transport.post_json(
            self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            payload={"model": self._model, "input": text[:4000]},
            timeout_seconds=timeout_seconds,
        )
        return _extract_embedding(response)


def build_click_history_text(
    *,
    titles: list[str],
    categories: list[str],
) -> str:
    parts = [title.strip() for title in titles if title and title.strip()]
    cats = [category.strip() for category in categories if category and category.strip()]
    return " | ".join([*parts[:20], *cats[:12]])[:2000]


def embed_user_history(
    *,
    titles: list[str],
    categories: list[str],
    click_history: list[int],
    client: EmbeddingClient | None,
    timeout_seconds: float = 8.0,
) -> list[float]:
    """
    Prefer LLM embedding of click history text; fall back to Gate 8 hash embedding.
    Output is always length EMBEDDING_DIM (projected if needed).
    """
    text = build_click_history_text(titles=titles, categories=categories)
    if client is not None and text:
        try:
            vector = client.embed(text, timeout_seconds=timeout_seconds)
            return _project_to_dim(vector, EMBEDDING_DIM)
        except Exception:  # noqa: BLE001
            logger.warning("LLM user embedding failed; using hash fallback")
    return compute_user_embedding(
        click_history=click_history,
        preferred_categories=categories,
    )


def _extract_embedding(response: Mapping[str, Any]) -> list[float]:
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise RuntimeError("embedding response missing data")
    first = data[0]
    if not isinstance(first, Mapping):
        raise RuntimeError("embedding item invalid")
    embedding = first.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise RuntimeError("embedding vector missing")
    return [float(value) for value in embedding]


def _project_to_dim(vector: list[float], dim: int) -> list[float]:
    if len(vector) == dim:
        return _l2_normalize(vector)
    if len(vector) > dim:
        # Average pool into dim buckets.
        bucket = len(vector) / dim
        projected = []
        for index in range(dim):
            start = int(index * bucket)
            end = int((index + 1) * bucket)
            chunk = vector[start:end] or [0.0]
            projected.append(sum(chunk) / len(chunk))
        return _l2_normalize(projected)
    padded = vector + [0.0] * (dim - len(vector))
    return _l2_normalize(padded)


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm < 1e-9:
        return empty_embedding()
    return [value / norm for value in vector]


def cache_key_for_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
    return f"personalization:llm_embed:v1:{digest}"


def dumps_embedding(vector: list[float]) -> str:
    return json.dumps(vector)
