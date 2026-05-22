# Glossary Candidate Review — Implementation Plan

## Overview

A second-stage review system that judges glossary candidates produced by `run_pipeline.py`
and stored in `glossary_candidates.db`. An OpenAI LLM (`gpt-4.1-mini`) evaluates each
candidate against 7 quality criteria and writes a verdict back to the DB. Designed to be
customer-agnostic: only `domain_context` changes between deployments.

---

## File Plan

### New files

```
review/
  __init__.py
  schemas.py      ← Pydantic models: CandidateJudgment, GlossaryVerdict, RejectionReason
  prompts.py      ← System/user prompt templates, domain_context builder
  judge.py        ← OpenAI Batch API calls, structured output, result parsing
run_review.py     ← CLI runner (mirrors run_pipeline.py in style)
```

### Existing files modified

| File | Change |
|---|---|
| `config.py` | Add `REVIEW_MODEL`, `OPENAI_API_KEY`, batch settings, verdict thresholds |
| `db/database.py` | Add `get_candidates_for_review()`, `bulk_update_judgments()` |
| `requirements.txt` | Add `openai`, confirm `pydantic` present |

### Untouched

`pipeline/`, `domain/`, `align.py`, `score.py`, `normalize.py` — review is a separate
stage that only reads from and writes to the DB.

---

## Judging Criteria (7 dimensions)

| # | Criterion | Type | Catches |
|---|---|---|---|
| 1 | **Source Term Cleanness** | 1–5 | Garbled phrases, concatenated spans, encoding artifacts |
| 2 | **Translation Pair Validity** | 1–5 | Trivial pairs (`polyester → polyester.`), truncated/partial translations |
| 3 | **Glossary Utility / Specificity** | 1–5 | Too generic (`space → tilaa`), too specific to a single product |
| 4 | **Domain Relevance for PIM** | 1–5 | Off-domain terms; driven by `domain_context` in system prompt |
| 5 | **Translation Consistency Value** | 1–5 | Would a glossary entry enforce anything a translator wouldn't already do? |
| 6 | **Translatability / Brand-Lock** | boolean | Brand names (`TENCEL®`, `GOTS`) → `verbatim_entry`, not a translation pair |
| 7 | **Cross-Locale Consistency** | derived | Pre-computed before API call; passed as context string to the LLM |

---

## Structured Output Schema

```python
class GlossaryVerdict(str, Enum):
    APPROVED = "approved"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    REJECTED = "rejected"
    VERBATIM_ENTRY = "verbatim_entry"   # keep source as-is, do not translate

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
    verdict: GlossaryVerdict
    confidence: float                       # 0.0–1.0
    source_term_cleanness: int              # 1–5
    translation_pair_validity: int          # 1–5
    glossary_utility: int                   # 1–5
    domain_relevance: int                   # 1–5
    translation_consistency_value: int      # 1–5
    rejection_reasons: list[RejectionReason]
    suggested_normalized_source: str | None # LLM may recover a cleaner form
    notes: str                              # ≤2 sentences, human-readable
```

---

## Batch Strategy (two-phase)

Minimises API calls by separating source-side from pair-side judgments.

### Phase 1 — Source term quality (~5K unique terms)

Judge per unique `source_term` regardless of locale:
- `source_term_cleanness`
- `glossary_utility`
- `domain_relevance`

If a source term is **rejected in Phase 1**, all its locale pairs are skipped entirely.
Only survivors proceed to Phase 2.

### Phase 2 — Translation pair quality (per locale pair)

For each surviving source × locale combination:
- `translation_pair_validity`
- `translation_consistency_value`
- `translatability / brand-lock`
- Cross-locale consistency signal (derived, passed as context)

### Why Batch API

- 50% cost reduction vs. synchronous calls
- Up to 50K requests per batch file — entire dataset fits in one submission
- Results available within 24 hours; `run_review.py` polls until complete

---

## System Prompt Template (customer-agnostic)

```
You are a translation glossary quality judge for a PIM (Product Information Management) system.

Customer domain: {domain_context}
Source language: {source_locale}
Target language: {target_locale}
PIM field: {field_origin}

Your task is to judge whether this term/translation pair should be included in the
official translation glossary. The glossary is used by translation automation (TMS)
to enforce consistent terminology across product descriptions.
```

**Kappahl**: `domain_context = "fashion apparel retail, Scandinavian market, sustainability-focused clothing brand"`

To adapt for another customer: change `domain_context` only. All criteria and schema remain identical.

---

## DB Write-Back

Verdicts map to existing `candidates` columns — no schema migration needed:

| Judgment field | DB column |
|---|---|
| `verdict` | `status` |
| `rejection_reasons` + `notes` | `reviewer_notes` (JSON-encoded) |
| `suggested_normalized_source` | `reviewer_notes` (included in JSON) |

Status values after review: `approved`, `needs_human_review`, `rejected`, `verbatim_entry`

---

## Implementation Order

1. `review/schemas.py` — Pydantic models (no dependencies)
2. `review/prompts.py` — prompt templates and context builder
3. `config.py` — add review config keys
4. `db/database.py` — add `get_candidates_for_review()`, `bulk_update_judgments()`
5. `review/judge.py` — batch file builder, API submission, result parser
6. `run_review.py` — CLI runner with `--phase`, `--locale`, `--limit` flags
7. `requirements.txt` — add `openai`
