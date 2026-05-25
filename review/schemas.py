"""Pydantic models for glossary candidate review judgments."""
from enum import Enum

from pydantic import BaseModel, Field


class GlossaryVerdict(str, Enum):
    APPROVED = "approved"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    REJECTED = "rejected"
    VERBATIM_ENTRY = "verbatim_entry"


class RejectionReason(str, Enum):
    TRIVIAL_PAIR = "trivial_pair"
    TRUNCATED_TARGET = "truncated_target"
    PARTIAL_TRANSLATION = "partial_translation"
    GARBLED_SOURCE = "garbled_source"
    TOO_GENERIC = "too_generic"
    OFF_DOMAIN = "off_domain"
    BRAND_NAME_VERBATIM = "brand_name_verbatim"
    LOW_CONSISTENCY_NEED = "low_consistency_need"


class CandidateJudgment(BaseModel):
    """Structured output from the LLM review of a glossary candidate."""

    verdict: GlossaryVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    source_term_cleanness: int = Field(ge=1, le=5)
    translation_pair_validity: int = Field(ge=1, le=5)
    glossary_utility: int = Field(ge=1, le=5)
    domain_relevance: int = Field(ge=1, le=5)
    translation_consistency_value: int = Field(ge=1, le=5)
    rejection_reasons: list[RejectionReason] = Field(default_factory=list)
    suggested_normalized_source: str | None = None
    notes: str = Field(max_length=500, description="1-2 sentences, human-readable")


class Phase1Judgment(BaseModel):
    """Phase 1: Source-term-only judgment (no locale pair context)."""

    verdict: GlossaryVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    source_term_cleanness: int = Field(ge=1, le=5)
    glossary_utility: int = Field(ge=1, le=5)
    domain_relevance: int = Field(ge=1, le=5)
    rejection_reasons: list[RejectionReason] = Field(default_factory=list)
    suggested_normalized_source: str | None = None
    notes: str = Field(max_length=500)


class Phase2Judgment(BaseModel):
    """Phase 2: Translation-pair judgment (locale-specific)."""

    verdict: GlossaryVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    translation_pair_validity: int = Field(ge=1, le=5)
    translation_consistency_value: int = Field(ge=1, le=5)
    is_brand_verbatim: bool = False
    rejection_reasons: list[RejectionReason] = Field(default_factory=list)
    notes: str = Field(max_length=500)
