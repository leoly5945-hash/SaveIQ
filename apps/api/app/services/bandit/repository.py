"""Persistence helpers for bandit decision logs and optional agent state."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.bandit import BanditLog

logger = logging.getLogger(__name__)


class BanditLogRepository:
    """Writes/reads bandit_logs. Opens its own session when none is provided."""

    def __init__(self, session_factory: Any = SessionLocal) -> None:
        self._session_factory = session_factory

    def insert_log(
        self,
        *,
        features: dict[str, Any],
        action: str,
        reward: float | None,
        user_id: str | None = None,
        rule_action: str | None = None,
        bandit_action: str | None = None,
        mode: str | None = None,
        applied: bool = False,
        explored: bool = False,
        latency_ms: float | None = None,
        estimated_cost_usd: float | None = None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
        db: Session | None = None,
    ) -> int | None:
        owns_session = db is None
        session = db or self._session_factory()
        try:
            row = BanditLog(
                features=features,
                action=action,
                reward=reward,
                user_id=user_id,
                rule_action=rule_action,
                bandit_action=bandit_action,
                mode=mode,
                applied=applied,
                explored=explored,
                latency_ms=latency_ms,
                estimated_cost_usd=estimated_cost_usd,
                confidence=confidence,
                event_metadata=metadata or {},
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist bandit log")
            session.rollback()
            return None
        finally:
            if owns_session:
                session.close()

    def fetch_training_logs(
        self,
        *,
        limit: int = 5000,
        require_reward: bool = True,
        db: Session | None = None,
    ) -> list[dict[str, Any]]:
        owns_session = db is None
        session = db or self._session_factory()
        try:
            stmt = select(BanditLog).order_by(BanditLog.id.asc()).limit(limit)
            if require_reward:
                stmt = stmt.where(BanditLog.reward.is_not(None))
            rows = session.scalars(stmt).all()
            return [
                {
                    "id": row.id,
                    "features": row.features,
                    "action": row.action,
                    "reward": row.reward,
                    "rule_action": row.rule_action,
                    "bandit_action": row.bandit_action,
                    "user_id": row.user_id,
                    "mode": row.mode,
                    "applied": row.applied,
                }
                for row in rows
            ]
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch bandit training logs")
            return []
        finally:
            if owns_session:
                session.close()

    def count_logs(self, db: Session | None = None) -> int:
        owns_session = db is None
        session = db or self._session_factory()
        try:
            total = session.scalar(select(func.count()).select_from(BanditLog))
            return int(total or 0)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to count bandit logs")
            return 0
        finally:
            if owns_session:
                session.close()
