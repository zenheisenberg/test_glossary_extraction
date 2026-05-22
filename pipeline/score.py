"""Scoring helpers for glossary candidates."""

from __future__ import annotations

from config import SCORING_WEIGHTS, FIELD_WEIGHTS, LABSE_STRONG, LABSE_REJECT
from domain.categories import DOMAIN_PRIORITY


def compute_final_score(candidate: dict, max_frequency: int = 10) -> float:
    """Compute the weighted final score for a glossary candidate."""
    labse_component = candidate["labse_score"]
    frequency_component = min(candidate.get("frequency", 1) / max_frequency, 1.0)
    field_weight_component = FIELD_WEIGHTS.get(candidate.get("field_origin", ""), 0.5)
    domain_priority_component = DOMAIN_PRIORITY.get(candidate.get("domain", "general"), 0.5)
    translation_consistency_component = candidate.get("translation_consistency", 0.5)
    brand_relevance_component = 1.0 if candidate.get("domain", "general") != "general" else 0.5

    final = (
        SCORING_WEIGHTS["labse"] * labse_component
        + SCORING_WEIGHTS["frequency"] * frequency_component
        + SCORING_WEIGHTS["field_weight"] * field_weight_component
        + SCORING_WEIGHTS["domain_priority"] * domain_priority_component
        + SCORING_WEIGHTS["translation_consistency"] * translation_consistency_component
        + SCORING_WEIGHTS["brand_relevance"] * brand_relevance_component
    )
    return round(final, 4)


def assign_review_status(final_score: float, labse_score: float) -> str:
    """Assign review status based on score thresholds."""
    if labse_score >= 0.85 and final_score >= 0.80:
        return "approved"
    if labse_score < 0.65:
        return "rejected"
    return "needs_review"
