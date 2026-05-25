# Glossary Extraction System

Automated extraction and LLM review of translation glossary candidates from Kappahl PIM product text.

Takes a multilingual Excel export from the PIM system, identifies candidate terminology pairs across five target locales, scores them using semantic similarity, and runs a two-phase LLM review to produce a vetted glossary ready for export to a TMS.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Process 1 — run\_pipeline](#process-1--run_pipeline)
  - [Stage 1 — Init Database](#stage-1--init-database)
  - [Stage 2 — Load NLP Model](#stage-2--load-nlp-model)
  - [Stage 3 — Load LaBSE Aligner](#stage-3--load-labse-aligner)
  - [Stage 4 — Ingest Excel](#stage-4--ingest-excel)
  - [Stage 5 — Pre-compute Source Terms](#stage-5--pre-compute-source-terms)
  - [Stage 6 — Align, Score, and Store](#stage-6--align-score-and-store)
- [Process 2 — run\_review](#process-2--run_review)
  - [Phase 1 — Source Term Quality](#phase-1--source-term-quality)
  - [Phase 2 — Translation Pair Quality](#phase-2--translation-pair-quality)
- [Status Lifecycle](#status-lifecycle)
- [Key Configuration](#key-configuration)
- [Database Schema](#database-schema)

---

## Overview

The system is split into two sequential CLI processes:

| Process | Entry Point | Purpose |
|---|---|---|
| **Pipeline** | `run_pipeline.py` | Ingest product text, extract terminology candidates, align across locales, score and store in SQLite |
| **Review** | `run_review.py` | LLM-powered two-phase quality review of stored candidates |

Both read from and write to the same SQLite database (`glossary_candidates.db`). The `status` column on each row acts as the handoff signal between the two processes.

```
Excel PIM export  →  run_pipeline.py  →  glossary_candidates.db  →  run_review.py  →  approved entries
```

---

## Project Structure

```
.
├── run_pipeline.py          # CLI entry point for extraction pipeline
├── run_review.py            # CLI entry point for LLM review
├── config.py                # All thresholds, paths, weights, and API settings
├── glossary_candidates.db   # SQLite output database
│
├── pipeline/
│   ├── ingest.py            # Excel loading and source/target pair extraction
│   ├── normalize.py         # Text cleaning (HTML, whitespace, fashion compounds)
│   ├── extract.py           # Term extraction via spaCy + KeyBERT/YAKE fallback
│   ├── filter.py            # Candidate filtering rules and blacklist
│   ├── align.py             # LaBSE semantic alignment (source terms → target phrases)
│   └── score.py             # Weighted final score and initial status assignment
│
├── review/
│   ├── judge.py             # LLM orchestration: Phase 1 and Phase 2 logic
│   ├── prompts.py           # System and user prompt templates
│   └── schemas.py           # Pydantic models for structured LLM output
│
├── domain/
│   ├── categories.py        # DOMAIN_TERMS seed lists and DOMAIN_PRIORITY weights
│   └── patterns.py          # spaCy Matcher patterns for fashion terminology
│
├── db/
│   └── database.py          # CandidateDB: SQLite wrapper with upsert and review helpers
│
└── export_glossary.py       # Export approved candidates to CSV
```

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m spacy download en_core_web_md
```

Create a `.env` file with your Azure OpenAI credentials (required for `run_review.py`):

```env
AZURE_OPENAI_ENDPOINT=https://<your-endpoint>.cognitiveservices.azure.com/openai/v1/
AZURE_OPENAI_KEY=<your-api-key>
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1-mini
```

---

## Process 1 — run\_pipeline

```bash
python run_pipeline.py [--excel-path PATH] [--db-path PATH] [--locales sv-SE fi-FI ...] [--batch-size 100] [--limit N]
```

Runs six sequential stages: from reading the Excel file to writing scored candidates into the database.

---

### Stage 1 — Init Database

Opens (or creates) `glossary_candidates.db` via `CandidateDB`. Applies the schema if it does not exist — a single `candidates` table with indexes on `status`, `target_locale`, `domain`, and `final_score`. WAL journal mode is enabled so the database remains readable while writes are in progress.

---

### Stage 2 — Load NLP Model

Loads the spaCy `en_core_web_md` English model as a process-scoped singleton (`pipeline/extract.py`). This model is used in Stage 5 to extract noun chunks and match domain-specific patterns from English source text.

---

### Stage 3 — Load LaBSE Aligner

Instantiates `LaBSEAligner` (`pipeline/align.py`), which lazy-loads the `sentence-transformers/LaBSE` multilingual embedding model. LaBSE produces language-agnostic dense embeddings — the mechanism that allows an English term to be matched against target-language text without a bilingual dictionary.

The aligner maintains an LRU cache (2048 entries) of target-text embeddings so that identical product descriptions seen across multiple source terms are only encoded once.

---

### Stage 4 — Ingest Excel

`pipeline/ingest.py` reads the `Item` sheet from the PIM Excel workbook. For every product row, it pairs each English text field (e.g. `ProductDescription_en`) with the equivalent field in each configured target locale (e.g. `ProductDescription_sv-SE`), producing a flat list of records:

```python
{
    "product_id":    "...",
    "field":         "ProductDescription",
    "source_locale": "en",
    "source_text":   "...",
    "target_locale": "sv-SE",
    "target_text":   "...",
}
```

Duplicate `(field, source_text, target_text)` triplets are deduplicated before the list is returned.

**Configured fields and their authority weights:**

| Field | Weight |
|---|---|
| `ProductNameShort`, `ProductSustainableMaterialcomposition` | 1.0 |
| `ProductFeatures` | 0.9 |
| `ProductDescription` | 0.8 |
| `ItemNameLong` | 0.7 |
| `ItemDescription` | 0.6 |
| `ItemUSP` | 0.5 |

**Target locales:** `sv-SE`, `fi-FI`, `de-DE`, `nb-NO`, `pl-PL`

---

### Stage 5 — Pre-compute Source Terms

Because English source text is locale-independent, this stage normalizes and extracts terms from every unique source text **once**, then caches the results. Without this cache, the same English paragraph would be re-processed by spaCy once per target locale (five times redundant work).

For each unique source text, the following sub-pipeline runs:

```
raw source text
    │
    ▼ normalize_text()
    Strip HTML tags, decode HTML entities, collapse whitespace,
    apply fashion compound rules (e.g. "T shirt" → "T-shirt",
    "wide leg" → "wide-leg"), standardize punctuation marks.
    │
    ▼ extract_terms()
    1. spaCy noun chunks
    2. Domain-specific Matcher patterns (pipeline/domain/patterns.py)
    3. Deduplicate overlapping spans — keep the longest
    4. Filter: 1–6 words, ≥ 3 characters
    5. Classify each term into a domain via DOMAIN_TERMS seed lists
       (O(1) exact match, substring fallback)
    6. Fallback to KeyBERT (top_n=10) + YAKE if fewer than 3 terms found
    │
    ▼ filter_candidates()
    - Strip numeric/percentage prefixes: "95% cotton" → "cotton"
    - Reject: stopwords, SKU codes, pure numbers, bare measurements,
      dimension labels (e.g. "43 cm height"), age ranges,
      marketing phrases, leading punctuation artifacts,
      and any term matching config.BLACKLIST
    - Deduplicate on normalized form
```

The result is a `{raw_source_text: (normalized_text, [term_dicts])}` in-memory cache.

---

### Stage 6 — Align, Score, and Store

The main loop iterates over each target locale, then each source/target pair within that locale.

**For each pair:**

**1. Retrieve** the pre-computed `(normalized_source, terms)` from the Stage 5 cache. Normalize the target text with the same `normalize_text()` pipeline.

**2. Align** source terms against the target text using `LaBSEAligner.align_terms()`:
- The target text is windowed into all contiguous n-grams of 1–4 tokens, generating candidate phrases.
- LaBSE encodes all source terms in a single batch and all target candidates in a single batch.
- A full cosine-similarity matrix `(S terms × C candidates)` is computed in one operation.
- Any pair with similarity ≥ `LABSE_REVIEW` (0.75) is retained as an alignment.

**3. Clean** both terms: strip leading/trailing punctuation via `strip_term_punctuation()`.

**4. Score** each aligned pair with `compute_final_score()`:

```
final_score = 0.30 × labse_score
            + 0.20 × min(frequency / 10, 1.0)
            + 0.15 × field_weight               (from config.FIELD_WEIGHTS)
            + 0.15 × domain_priority            (from domain.categories.DOMAIN_PRIORITY)
            + 0.10 × translation_consistency    (defaults to 0.5 until reviewed)
            + 0.10 × brand_relevance            (1.0 if domain ≠ "general", else 0.5)
```

**5. Assign initial status** via `assign_review_status()`:

| Condition | Status |
|---|---|
| LaBSE ≥ 0.85 **and** final score ≥ 0.80 | `approved` |
| LaBSE < 0.65 | `rejected` |
| Everything else | `needs_review` |

**6. Batch upsert** into the `candidates` table every 100 rows (configurable via `--batch-size`). On conflict on `(source_locale, target_locale, normalized_source, domain)`, the existing row's `frequency` is incremented and scores are MAX-updated — so repeated evidence of the same term strengthens its score rather than creating duplicates.

---

## Process 2 — run\_review

```bash
# Phase 1: evaluate source term quality
python run_review.py --phase 1 [--limit 500]

# Phase 2: evaluate translation pair quality (optionally scoped to one locale)
python run_review.py --phase 2 [--locale sv-SE] [--limit 500]
```

The review stage is split into two independent phases. Phase 1 evaluates source terms in isolation (locale-agnostic). Phase 2 evaluates the full translation pair per locale, but only for terms that passed Phase 1.

LLM calls are made to Azure OpenAI (Foundry) via the standard OpenAI Python SDK. Up to 5 requests run concurrently. Each call retries up to 3 times with exponential backoff on transient failures. Responses are parsed into Pydantic models (`review/schemas.py`) for strict validation before writing to the database.

---

### Phase 1 — Source Term Quality

**Fetch:** Queries for distinct `normalized_source` values where `status = 'needs_review'`, ordered by frequency descending so the most-evidenced terms are reviewed first.

**Judge:** For each source term the LLM is asked to evaluate three dimensions on a 1–5 scale:

| Dimension | What it measures |
|---|---|
| `source_term_cleanness` | Is the term well-formed? Not garbled, not an encoding artifact. |
| `glossary_utility` | Is it specific enough to be useful in a TMS glossary? Not too generic (e.g. "space"). |
| `domain_relevance` | Is it relevant to the fashion/apparel PIM domain? |

**Verdict logic (applied by the LLM):**

| Condition | Verdict |
|---|---|
| `cleanness < 3` | `rejected` — reason: `garbled_source` |
| `utility < 2` | `rejected` — reason: `too_generic` |
| `domain_relevance < 2` | `rejected` — reason: `off_domain` |
| All scores ≥ 4 | `approved` |
| Brand name (TENCEL®, GOTS, Lycra…) | `verbatim_entry` |
| Otherwise | `needs_human_review` |

**Resulting DB status:**

| LLM verdict | DB `status` |
|---|---|
| `approved` | `phase1_approved` |
| `needs_human_review` | `phase1_needs_human_review` |
| `rejected` | `phase1_rejected` |
| `verbatim_entry` | `phase1_verbatim_entry` |

**Write-back:** `bulk_update_judgments()` updates **all** rows sharing the same `normalized_source` in a single transaction — a single LLM call approves or rejects the source term across all locales and fields simultaneously. The full JSON judgment (scores, confidence, notes, rejection reasons) is stored in `reviewer_notes`.

---

### Phase 2 — Translation Pair Quality

**Fetch:** Queries for individual candidate rows where `status IN ('phase1_approved', 'phase1_verbatim_entry')`, optionally filtered to a single `target_locale`.

**Judge:** For each `(source_term, target_term, locale)` row the LLM evaluates two dimensions:

| Dimension | What it measures |
|---|---|
| `translation_pair_validity` | Is the translation correct and complete? Not trivial (e.g. "polyester → polyester"), not truncated. |
| `translation_consistency_value` | Would a glossary entry enforce anything a translator wouldn't already do automatically? |

The prompt is locale-specific and includes: source/target terms, locale codes, field origin, frequency count, and LaBSE similarity score. If the term was tagged `phase1_verbatim_entry`, an additional hint instructs the LLM to verify whether keeping the term untranslated is appropriate in the target locale.

**Verdict logic (applied by the LLM):**

| Condition | Verdict |
|---|---|
| `pair_validity < 2` | `rejected` — reason: `trivial_pair` or `truncated_target` |
| `consistency_value < 2` | `rejected` — reason: `low_consistency_need` |
| Brand that should stay verbatim | `verbatim_entry` |
| Both scores ≥ 4 | `approved` |
| Otherwise | `needs_human_review` |

**Resulting DB status:**

| LLM verdict | DB `status` |
|---|---|
| `approved` | `approved` ✅ |
| `needs_human_review` | `phase2_needs_human_review` |
| `rejected` | `phase2_rejected` |
| `verbatim_entry` | `phase2_verbatim_entry` |

**Write-back:** Updates by candidate `id` (not by source term) so each locale pair is judged and stored independently.

Rows with `status = 'approved'` are the final vetted glossary entries, ready for export via `export_glossary.py`.

---

## Status Lifecycle

```
                     ┌───────────────────────────────────┐
                     │          run_pipeline.py           │
                     └───────────────────────────────────┘
                                       │
                             Excel row per locale
                                       │
                         ┌─────────────▼────────────┐
                         │  Normalize → Extract     │
                         │  → Filter → Align        │
                         │  → Score                 │
                         └─────────────┬────────────┘
                                       │
              ┌────────────────────────┼───────────────────────┐
              │                        │                       │
       labse < 0.65            0.65 ≤ labse < 0.85      labse ≥ 0.85
       OR score < 0.80          OR score < 0.80         AND score ≥ 0.80
              │                        │                       │
         [rejected]            [needs_review]             [approved]
                                       │
                     ┌─────────────────▼─────────────────┐
                     │      run_review.py --phase 1       │
                     └─────────────────┬─────────────────┘
                                       │
         ┌─────────────────────────────┼──────────────────────────┐
         │                             │                          │
 [phase1_rejected]         [phase1_needs_human_review]  [phase1_approved]
                                                         [phase1_verbatim_entry]
                                                                  │
                                    ┌─────────────────────────────▼───────────┐
                                    │        run_review.py --phase 2          │
                                    └─────────────────────────────┬───────────┘
                                                                  │
                          ┌───────────────────────┬──────────────────────────┐
                          │                       │                          │
                 [phase2_rejected]   [phase2_needs_human_review]        [approved] ✅
                                                                    [phase2_verbatim_entry]
```

---

## Key Configuration

All thresholds, paths, and model settings live in `config.py`.

| Setting | Default | Description |
|---|---|---|
| `EXCEL_PATH` | `.implementation_files/Produkttexter_Kappahl_...xlsx` | Source PIM export |
| `DB_PATH` | `glossary_candidates.db` | SQLite output |
| `SOURCE_LOCALE` | `en` | Source language |
| `TARGET_LOCALES` | `sv-SE, fi-FI, de-DE, nb-NO, pl-PL` | Target languages |
| `LABSE_REVIEW` | `0.75` | Minimum cosine similarity to create a candidate |
| `LABSE_STRONG` | `0.85` | Threshold for auto-approval during pipeline |
| `LABSE_REJECT` | `0.65` | Threshold for auto-rejection during pipeline |
| `MAX_TERM_WORDS` | `6` | Maximum words per term |
| `MIN_TERM_CHARS` | `3` | Minimum characters per term |
| `REVIEW_MODEL` | `gpt-4.1-mini` | Azure OpenAI deployment used for LLM review |
| `REVIEW_BATCH_SIZE` | `20` | Candidates per LLM API call |
| `REVIEW_MAX_CONCURRENT` | `5` | Parallel LLM requests |
| `REVIEW_MAX_RETRIES` | `3` | Retries on transient API failures |
| `REVIEW_TIMEOUT_SECONDS` | `60` | Per-request timeout |

**Scoring weights (`SCORING_WEIGHTS`):**

| Component | Weight |
|---|---|
| LaBSE similarity | 30% |
| Frequency (capped at 10 occurrences) | 20% |
| Field authority weight | 15% |
| Domain priority | 15% |
| Translation consistency | 10% |
| Brand/domain relevance | 10% |

---

## Database Schema

```sql
CREATE TABLE candidates (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_locale        TEXT NOT NULL,
    target_locale        TEXT NOT NULL,
    source_term          TEXT NOT NULL,
    target_term          TEXT NOT NULL,
    normalized_source    TEXT NOT NULL,
    normalized_target    TEXT NOT NULL,
    domain               TEXT,
    category             TEXT,
    field_origin         TEXT,
    frequency            INTEGER DEFAULT 1,
    labse_score          REAL,
    final_score          REAL,
    status               TEXT DEFAULT 'needs_review',
    source_context       TEXT,
    target_context       TEXT,
    evidence_product_ids TEXT,    -- JSON array of product IDs
    reviewer_notes       TEXT,    -- JSON judgment from LLM review
    created_at           TEXT,
    updated_at           TEXT,
    UNIQUE(source_locale, target_locale, normalized_source, domain)
);
```

**Indexes:** `status`, `target_locale`, `domain`, `final_score DESC`

**Conflict resolution:** On duplicate `(source_locale, target_locale, normalized_source, domain)`, `frequency` is incremented and `labse_score` / `final_score` are MAX-updated.
