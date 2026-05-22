"""Kappahl Glossary Extraction Pipeline v2 - CLI Runner.

Orchestrates: ingest → normalize → extract → filter → align → score → store.
Output: SQLite database with glossary candidates ready for review.
"""
import argparse
import sys
import time
from pathlib import Path
from tqdm import tqdm

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    EXCEL_PATH, DB_PATH, SOURCE_LOCALE, TARGET_LOCALES, FIELD_WEIGHTS,
    LABSE_REVIEW,
)
from db.database import CandidateDB
from pipeline.ingest import load_excel, get_field_locale_pairs
from pipeline.normalize import normalize_text
from pipeline.extract import extract_terms, load_nlp
from pipeline.filter import filter_candidates
from pipeline.align import LaBSEAligner
from pipeline.score import compute_final_score, assign_review_status


def _stage(label: str, step: int, total_steps: int) -> float:
    """Print a stage header and return the current timestamp."""
    print(f"\n[{step}/{total_steps}] {label}...")
    return time.time()


def _stage_done(t0: float) -> None:
    """Print elapsed time for the last stage."""
    print(f"  > done ({time.time() - t0:.1f}s)")


def run_pipeline(excel_path: str = None, db_path: str = None,
                 locales: list[str] = None, batch_size: int = 100,
                 limit: int = None):
    """Run the full glossary extraction pipeline."""
    excel_path = Path(excel_path) if excel_path else EXCEL_PATH
    db_path = Path(db_path) if db_path else DB_PATH
    locales = locales or TARGET_LOCALES

    TOTAL_STAGES = 6

    print(f"=== Kappahl Glossary Extraction Pipeline v2 ===")
    print(f"Source:          {excel_path}")
    print(f"Database:        {db_path}")
    print(f"Target locales:  {locales}")

    # ── Stage 1: Init DB ──────────────────────────────────────────────────────
    t0 = _stage("Init database", 1, TOTAL_STAGES)
    db = CandidateDB(db_path)
    _stage_done(t0)

    # ── Stage 2: Load NLP model ───────────────────────────────────────────────
    t0 = _stage("Load spaCy NLP model", 2, TOTAL_STAGES)
    nlp = load_nlp()
    _stage_done(t0)

    # ── Stage 3: Load LaBSE aligner ───────────────────────────────────────────
    t0 = _stage("Load LaBSE aligner", 3, TOTAL_STAGES)
    aligner = LaBSEAligner()
    _stage_done(t0)

    # ── Stage 4: Ingest Excel ─────────────────────────────────────────────────
    t0 = _stage("Load Excel data", 4, TOTAL_STAGES)
    df = load_excel(excel_path)
    pairs = get_field_locale_pairs(df)

    if limit:
        pairs = pairs[:limit]

    _stage_done(t0)
    print(f"  > {len(pairs)} source-target text pairs to process")

    # Summarise work ahead
    locale_counts = {
        loc: len([p for p in pairs if p["target_locale"] == loc])
        for loc in locales
    }
    active_locales = [loc for loc in locales if locale_counts[loc] > 0]
    total_pairs = sum(locale_counts[loc] for loc in active_locales)

    print(f"  > Locales to process: {len(active_locales)}  "
          f"({', '.join(f'{l}={locale_counts[l]}' for l in active_locales)})")

    # ── Stage 5: Pre-compute source terms (locale-independent) ───────────────
    # The source-side pipeline (normalize → extract → filter) is identical for
    # every locale. Without this cache, the same English text would be parsed
    # by spaCy once per locale — 5× redundant work for 5 target locales.
    t0 = _stage("Pre-compute source terms", 5, TOTAL_STAGES)

    unique_raw_sources = list({p["source_text"] for p in pairs})
    source_term_cache: dict[str, tuple[str, list[dict]]] = {}

    for raw_src in tqdm(unique_raw_sources, desc="  source cache", unit="texts", leave=False):
        normalized = normalize_text(raw_src)
        terms = filter_candidates(extract_terms(normalized, nlp=nlp)) if normalized else []
        source_term_cache[raw_src] = (normalized, terms)

    skipped = sum(1 for _, terms in source_term_cache.values() if not terms)
    _stage_done(t0)
    print(f"  > {len(unique_raw_sources)} unique source texts cached  "
          f"({skipped} yielded no terms — will be skipped during processing)")

    # ── Stage 6: Process pairs ────────────────────────────────────────────────
    print(f"\n[{TOTAL_STAGES}/{TOTAL_STAGES}] Align → Score → Store")

    total_candidates = 0
    pipeline_start = time.time()

    # Single master bar spanning ALL locales / ALL pairs
    with tqdm(
        total=total_pairs,
        unit="pairs",
        bar_format=(
            "{l_bar}{bar}| {n_fmt}/{total_fmt} pairs "
            "[{elapsed}<{remaining}, {rate_fmt}]"
        ),
        dynamic_ncols=True,
    ) as pbar:
        for locale_idx, target_locale in enumerate(active_locales, start=1):
            locale_pairs = [p for p in pairs if p["target_locale"] == target_locale]

            candidates_batch = []

            for pair in locale_pairs:
                pbar.set_description(
                    f"locale {locale_idx}/{len(active_locales)} [{target_locale}]"
                )

                # Source: look up pre-computed result (normalize + extract + filter
                # already done in stage 5 — no repeated spaCy work per locale)
                source_text, terms = source_term_cache[pair["source_text"]]

                # Normalize target (locale-specific — must be done here)
                target_text = normalize_text(pair["target_text"])

                if not source_text or not target_text or not terms:
                    pbar.update(1)
                    continue

                # Align source terms with target text
                source_term_texts = [t["term"] for t in terms]
                alignments = aligner.align_terms(
                    source_terms=source_term_texts,
                    target_texts=[target_text],
                    threshold=LABSE_REVIEW,
                )

                # Build candidates
                for alignment in alignments:
                    term_dict = next(
                        (t for t in terms if t["term"] == alignment["source_term"]),
                        {}
                    )

                    candidate = {
                        "source_locale": SOURCE_LOCALE,
                        "target_locale": target_locale,
                        "source_term": alignment["source_term"],
                        "target_term": alignment["target_term"],
                        "normalized_source": alignment["source_term"].lower().strip(),
                        "normalized_target": alignment["target_term"].lower().strip(),
                        "domain": term_dict.get("domain", "general"),
                        "category": term_dict.get("domain", "general"),
                        "field_origin": pair["field"],
                        "frequency": 1,
                        "labse_score": alignment["labse_score"],
                        "source_context": source_text,
                        "target_context": target_text,
                        "evidence_product_ids": [pair["product_id"]],
                    }

                    # Score
                    candidate["final_score"] = compute_final_score(candidate)
                    candidate["status"] = assign_review_status(
                        candidate["final_score"], candidate["labse_score"]
                    )

                    candidates_batch.append(candidate)

                # Flush batch
                if len(candidates_batch) >= batch_size:
                    db.bulk_upsert(candidates_batch)
                    total_candidates += len(candidates_batch)
                    candidates_batch = []

                pbar.update(1)

            # Flush remaining for this locale
            if candidates_batch:
                db.bulk_upsert(candidates_batch)
                total_candidates += len(candidates_batch)
                candidates_batch = []

            tqdm.write(
                f"  ✓ {target_locale} complete  "
                f"({locale_counts[target_locale]} pairs, "
                f"{locale_idx}/{len(active_locales)} locales done)"
            )

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = time.time() - pipeline_start
    print()
    print(f"=== Pipeline Complete ===")
    print(f"Total pairs processed:   {total_pairs}")
    print(f"Total candidates stored: {total_candidates}")
    print(f"Total elapsed time:      {elapsed:.1f}s")
    stats = db.get_stats()
    print(f"Database stats: {stats}")
    db.close()
    print(f"\nResults saved to: {db_path}")


def main():
    parser = argparse.ArgumentParser(description="Kappahl Glossary Extraction Pipeline v2")
    parser.add_argument("--excel-path", type=str, default=None,
                        help="Path to Excel file (default: from config)")
    parser.add_argument("--db-path", type=str, default=None,
                        help="Path to SQLite database (default: from config)")
    parser.add_argument("--locales", nargs="+", default=None,
                        help="Target locales to process (default: all)")
    parser.add_argument("--batch-size", type=int, default=100,
                        help="Batch size for DB writes")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of text pairs to process (for testing)")
    args = parser.parse_args()

    run_pipeline(
        excel_path=args.excel_path,
        db_path=args.db_path,
        locales=args.locales,
        batch_size=args.batch_size,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
