"""Request-scoped A/B assignment (Gate 10D)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_ab_user_id: ContextVar[str | None] = ContextVar("ab_user_id", default=None)
_ab_group: ContextVar[str] = ContextVar("ab_group", default="none")
_ab_experiment: ContextVar[str | None] = ContextVar("ab_experiment", default=None)
_ab_overrides: ContextVar[dict[str, Any] | None] = ContextVar("ab_overrides", default=None)


def bind_abtest_request(
    *,
    user_id: str | None,
    group: str,
    experiment: str | None,
    overrides: dict[str, Any] | None,
) -> None:
    _ab_user_id.set(user_id)
    _ab_group.set(group or "none")
    _ab_experiment.set(experiment)
    _ab_overrides.set(overrides)


def clear_abtest_request() -> None:
    _ab_user_id.set(None)
    _ab_group.set("none")
    _ab_experiment.set(None)
    _ab_overrides.set(None)


def get_ab_user_id() -> str | None:
    return _ab_user_id.get()


def get_ab_group() -> str:
    return _ab_group.get() or "none"


def get_ab_experiment() -> str | None:
    return _ab_experiment.get()


def get_ab_overrides() -> dict[str, Any] | None:
    return _ab_overrides.get()
