"""Personalization helpers: ranking boost from preferred categories."""

from __future__ import annotations

from typing import Any

from app.services.user.profile import UserProfile


def apply_personalization_boost(
    results: list[Any],
    profile: UserProfile | None,
) -> list[Any]:
    """
    Stable soft re-rank: preferred-category matches rise while relative order among
    equal boost tiers is preserved. No-op when personalization is inactive.
    """
    if profile is None or not profile.personalization_active:
        return results
    preferred = {item.strip().lower() for item in profile.preferred_categories if item}
    if not preferred:
        return results

    decorated: list[tuple[int, int, Any]] = []
    for index, row in enumerate(results):
        category = ""
        if isinstance(row, dict):
            category = str(row.get("category") or "").strip().lower()
        boost = 1 if category and category in preferred else 0
        decorated.append((-boost, index, row))
    decorated.sort(key=lambda item: (item[0], item[1]))
    reranked: list[Any] = []
    for _boost, _index, row in decorated:
        if not isinstance(row, dict):
            reranked.append(row)
            continue
        explanation = dict(row.get("decision_explanation") or {})
        reasons = list(explanation.get("ranking_signals") or [])
        category = str(row.get("category") or "").strip().lower()
        if category and category in preferred:
            note = f"personalized category boost: {category}"
            if note not in reasons:
                reasons.append(note)
            explanation["ranking_signals"] = reasons
            summary = str(explanation.get("summary") or "")
            if "personalized" not in summary.lower():
                explanation["summary"] = (
                    f"{summary} Personalized for anonymous preferences.".strip()
                )
            row = {**row, "decision_explanation": explanation}
        reranked.append(row)
    return reranked
