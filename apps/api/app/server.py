"""Render-friendly API startup entrypoint."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import uvicorn


def run_migrations(*, attempts: int = 8, delay_seconds: float = 3.0) -> None:
    """Apply Alembic migrations with retries for cold Postgres starts."""
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            print(f"alembic_upgrade attempt={attempt}/{attempts}", flush=True)
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                check=True,
            )
            print("alembic_upgrade=ok", flush=True)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            print(
                f"alembic_upgrade=error attempt={attempt} returncode={exc.returncode}",
                flush=True,
            )
            if attempt < attempts:
                time.sleep(delay_seconds)
    raise SystemExit(
        f"alembic upgrade failed after {attempts} attempts: {last_error}"
    ) from last_error


def main() -> None:
    run_migrations()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
