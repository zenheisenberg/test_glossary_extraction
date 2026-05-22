"""CLI runner for the glossary candidate LLM review stage.

Usage:
    python run_review.py --phase 1 --limit 100
    python run_review.py --phase 2 --locale sv-SE --limit 500
"""
import argparse
import logging
import sys

from config import DB_PATH
from db.database import CandidateDB
from review.judge import review_phase1, review_phase2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Run LLM review on glossary candidates."
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2],
        required=True,
        help="Review phase: 1=source term quality, 2=translation pair quality",
    )
    parser.add_argument(
        "--locale",
        type=str,
        default=None,
        help="Target locale filter (Phase 2 only), e.g. 'sv-SE'",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of candidates to review (default: 500)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(DB_PATH),
        help="Path to the glossary candidates database",
    )
    args = parser.parse_args()

    # Open DB
    db = CandidateDB(args.db)

    try:
        stats = db.get_stats()
        logger.info("DB stats before review: %s", stats)

        # Fetch candidates
        candidates = db.get_candidates_for_review(
            phase=args.phase,
            target_locale=args.locale,
            limit=args.limit,
        )
        logger.info(
            "Fetched %d candidates for Phase %d review", len(candidates), args.phase
        )

        if not candidates:
            logger.info("No candidates to review. Exiting.")
            return

        # Run LLM review
        if args.phase == 1:
            judgments = review_phase1(candidates)
        else:
            judgments = review_phase2(candidates, target_locale=args.locale)

        # Write results back to DB
        updated = db.bulk_update_judgments(judgments)
        logger.info("Updated %d candidates in DB", updated)

        # Summary
        stats_after = db.get_stats()
        logger.info("DB stats after review: %s", stats_after)

    finally:
        db.close()


if __name__ == "__main__":
    main()
