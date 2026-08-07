"""Request-scoped canary identity (Gate 10C)."""

from __future__ import annotations

from contextvars import ContextVar

_canary_identity: ContextVar[str | None] = ContextVar("canary_identity", default=None)
_canary_cohort: ContextVar[str] = ContextVar("canary_cohort", default="off")


def bind_canary_request(*, identity: str | None, cohort: str) -> None:
    _canary_identity.set(identity)
    _canary_cohort.set(cohort)


def clear_canary_request() -> None:
    _canary_identity.set(None)
    _canary_cohort.set("off")


def get_canary_identity() -> str | None:
    return _canary_identity.get()


def get_canary_cohort_label() -> str:
    return _canary_cohort.get() or "off"
