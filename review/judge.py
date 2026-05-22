"""LLM judge for glossary candidates using Azure OpenAI (Foundry endpoint).

Uses the standard OpenAI Python SDK with base_url pointed at the Azure Foundry
cognitiveservices endpoint. Authentication is via API key (not Azure AD).
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    REVIEW_BATCH_SIZE,
    REVIEW_DOMAIN_CONTEXT,
    REVIEW_MAX_CONCURRENT,
    REVIEW_MAX_RETRIES,
    REVIEW_MODEL,
    REVIEW_TIMEOUT_SECONDS,
    SOURCE_LOCALE,
)
from review.prompts import (
    build_system_prompt_phase1,
    build_system_prompt_phase2,
    build_user_prompt_phase1,
    build_user_prompt_phase2,
)
from review.schemas import Phase1Judgment, Phase2Judgment

logger = logging.getLogger(__name__)


def _get_client() -> OpenAI:
    """Create an OpenAI client configured for the Azure Foundry endpoint."""
    return OpenAI(
        base_url=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
    )


def _call_llm(client: OpenAI, system_prompt: str, user_prompt: str) -> str | None:
    """Make a single chat completion call with retries."""
    for attempt in range(1, REVIEW_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=REVIEW_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=512,
                timeout=REVIEW_TIMEOUT_SECONDS,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(
                "LLM call attempt %d/%d failed: %s", attempt, REVIEW_MAX_RETRIES, e
            )
            if attempt < REVIEW_MAX_RETRIES:
                time.sleep(2 ** attempt)  # exponential backoff
    return None


def _parse_phase1_response(raw: str | None) -> Phase1Judgment | None:
    """Parse Phase 1 JSON response into a validated Pydantic model."""
    if not raw:
        return None
    try:
        # Strip markdown fencing if model wraps it
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(text)
        return Phase1Judgment.model_validate(data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse Phase 1 response: %s | raw: %s", e, raw[:200])
        return None


def _parse_phase2_response(raw: str | None) -> Phase2Judgment | None:
    """Parse Phase 2 JSON response into a validated Pydantic model."""
    if not raw:
        return None
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(text)
        return Phase2Judgment.model_validate(data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse Phase 2 response: %s | raw: %s", e, raw[:200])
        return None


# ---------------------------------------------------------------------------
# Phase 1 — Source term quality review
# ---------------------------------------------------------------------------


def review_phase1(candidates: list[dict]) -> list[dict]:
    """Judge source terms (Phase 1).

    Args:
        candidates: list of dicts from get_candidates_for_review(phase=1).
            Each has: source_term, source_locale, frequency, field_origins, domains.

    Returns:
        list of judgment dicts ready for bulk_update_judgments():
            {source_term, status, reviewer_notes}
    """
    client = _get_client()
    system_prompt = build_system_prompt_phase1(
        domain_context=REVIEW_DOMAIN_CONTEXT,
        source_locale=SOURCE_LOCALE,
    )

    results: list[dict] = []

    def _judge_one(candidate: dict) -> dict | None:
        user_prompt = build_user_prompt_phase1(
            source_term=candidate["source_term"],
            frequency=candidate["frequency"],
            field_origins=candidate.get("field_origins", "unknown"),
        )
        raw = _call_llm(client, system_prompt, user_prompt)
        judgment = _parse_phase1_response(raw)
        if not judgment:
            return None

        # Map verdict to DB status
        status_map = {
            "approved": "phase1_approved",
            "needs_human_review": "needs_human_review",
            "rejected": "rejected",
            "verbatim_entry": "verbatim_entry",
        }

        return {
            "source_term": candidate["source_term"],
            "status": status_map.get(judgment.verdict.value, "needs_human_review"),
            "reviewer_notes": json.dumps(judgment.model_dump(), ensure_ascii=False),
        }

    # Process concurrently in batches
    with ThreadPoolExecutor(max_workers=REVIEW_MAX_CONCURRENT) as executor:
        futures = {
            executor.submit(_judge_one, c): c for c in candidates
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
            else:
                c = futures[future]
                logger.warning("Failed to judge source term: %s", c["source_term"])

    logger.info("Phase 1 complete: %d/%d candidates judged", len(results), len(candidates))
    return results


# ---------------------------------------------------------------------------
# Phase 2 — Translation pair review
# ---------------------------------------------------------------------------


def review_phase2(candidates: list[dict], target_locale: str | None = None) -> list[dict]:
    """Judge translation pairs (Phase 2).

    Args:
        candidates: list of dicts from get_candidates_for_review(phase=2).
            Each is a full candidate row dict.
        target_locale: if provided, used in prompt context.

    Returns:
        list of judgment dicts ready for bulk_update_judgments():
            {id, status, reviewer_notes}
    """
    client = _get_client()
    results: list[dict] = []

    def _judge_one(candidate: dict) -> dict | None:
        tgt_locale = candidate.get("target_locale", target_locale or "unknown")
        system_prompt = build_system_prompt_phase2(
            domain_context=REVIEW_DOMAIN_CONTEXT,
            source_locale=candidate.get("source_locale", SOURCE_LOCALE),
            target_locale=tgt_locale,
            field_origin=candidate.get("field_origin", "unknown"),
            cross_locale_context="No cross-locale data available.",
        )
        user_prompt = build_user_prompt_phase2(
            source_term=candidate.get("source_term", candidate.get("normalized_source", "")),
            target_term=candidate.get("target_term", candidate.get("normalized_target", "")),
            source_locale=candidate.get("source_locale", SOURCE_LOCALE),
            target_locale=tgt_locale,
            field_origin=candidate.get("field_origin", "unknown"),
            frequency=candidate.get("frequency", 1),
            labse_score=candidate.get("labse_score", 0.0) or 0.0,
        )
        raw = _call_llm(client, system_prompt, user_prompt)
        judgment = _parse_phase2_response(raw)
        if not judgment:
            return None

        # Map verdict to DB status
        status_map = {
            "approved": "approved",
            "needs_human_review": "needs_human_review",
            "rejected": "rejected",
            "verbatim_entry": "verbatim_entry",
        }

        return {
            "id": candidate["id"],
            "status": status_map.get(judgment.verdict.value, "needs_human_review"),
            "reviewer_notes": json.dumps(judgment.model_dump(), ensure_ascii=False),
        }

    with ThreadPoolExecutor(max_workers=REVIEW_MAX_CONCURRENT) as executor:
        futures = {
            executor.submit(_judge_one, c): c for c in candidates
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
            else:
                c = futures[future]
                logger.warning(
                    "Failed to judge pair: %s → %s",
                    c.get("source_term", "?"),
                    c.get("target_term", "?"),
                )

    logger.info("Phase 2 complete: %d/%d candidates judged", len(results), len(candidates))
    return results
