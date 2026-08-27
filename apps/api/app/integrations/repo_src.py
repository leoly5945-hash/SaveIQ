"""Put repo-root ``src/`` on ``sys.path`` so ``from src.affiliate…`` works.

Walks parents of this file until ``src/affiliate`` or ``src/router`` exists
(local: repo root; Docker: ``/app`` after ``COPY src ./src``).
"""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_src_on_path() -> None:
    here = Path(__file__).resolve()
    candidates: list[Path] = [Path("/app")]
    for parent in here.parents:
        candidates.append(parent)
    for root in candidates:
        if (root / "src" / "affiliate").is_dir() or (root / "src" / "router").is_dir():
            path = str(root)
            if path not in sys.path:
                sys.path.insert(0, path)
            return
