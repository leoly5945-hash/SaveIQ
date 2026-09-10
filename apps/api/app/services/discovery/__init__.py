"""Discovery (Layer 3, entry) — a natural-language shopping request becomes a
structured query and a list of candidate products to run through the engine.

``query.parse_shopping_query`` is rule-based today (no LLM); an LLM parser via
:mod:`app.services.router` is the next step once a provider key is configured.
"""

from app.services.discovery.discover import DiscoverHit, DiscoverResult, discover
from app.services.discovery.query import ShoppingQuery, parse_shopping_query

__all__ = [
    "DiscoverHit",
    "DiscoverResult",
    "ShoppingQuery",
    "discover",
    "parse_shopping_query",
]
