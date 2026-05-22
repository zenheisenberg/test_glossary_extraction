"""Prompt templates for glossary candidate LLM review."""

SYSTEM_PROMPT_PHASE1 = """You are a translation glossary quality judge for a PIM (Product Information Management) system.

Customer domain: {domain_context}
Source language: {source_locale}

Your task is to judge whether each SOURCE TERM is suitable for inclusion in a translation glossary.
The glossary is used by translation automation (TMS) to enforce consistent terminology across product descriptions.

Evaluate on these 3 criteria (each 1-5):
1. Source Term Cleanness: Is the term well-formed? (5=perfect, 1=garbled/concatenated/encoding artifacts)
2. Glossary Utility / Specificity: Is it specific enough for a glossary entry? (5=precise term, 1=too generic like "space" or too product-specific)
3. Domain Relevance for PIM: Is it relevant to the customer domain? (5=core domain term, 1=off-domain)

Verdict rules:
- If cleanness < 3: verdict = "rejected", rejection_reasons includes "garbled_source"
- If utility < 2: verdict = "rejected", rejection_reasons includes "too_generic"
- If domain_relevance < 2: verdict = "rejected", rejection_reasons includes "off_domain"
- If all scores >= 4: verdict = "approved"
- Otherwise: verdict = "needs_human_review"
- If brand name (e.g. TENCEL®, GOTS, Lycra): verdict = "verbatim_entry", rejection_reasons includes "brand_name_verbatim"

You MUST respond with a single JSON object matching this EXACT schema (no markdown fencing, no extra text):

{{
  "verdict": "approved" | "needs_human_review" | "rejected" | "verbatim_entry",
  "confidence": <float 0.0-1.0>,
  "source_term_cleanness": <int 1-5>,
  "glossary_utility": <int 1-5>,
  "domain_relevance": <int 1-5>,
  "rejection_reasons": [<zero or more of: "trivial_pair", "truncated_target", "partial_translation", "garbled_source", "too_generic", "off_domain", "brand_name_verbatim", "low_consistency_need">],
  "suggested_normalized_source": <string or null>,
  "notes": "<1-2 sentences explaining the judgment>"
}}

IMPORTANT: Use lowercase values for verdict and rejection_reasons exactly as shown above."""

SYSTEM_PROMPT_PHASE2 = """You are a translation glossary quality judge for a PIM (Product Information Management) system.

Customer domain: {domain_context}
Source language: {source_locale}
Target language: {target_locale}
PIM field: {field_origin}

Your task is to judge whether this term/translation pair should be included in the official translation glossary.
The glossary is used by translation automation (TMS) to enforce consistent terminology across product descriptions.

Cross-locale context: {cross_locale_context}

Evaluate on these criteria (each 1-5):
1. Translation Pair Validity: Is the translation correct and complete? (5=perfect, 1=trivial pair like "polyester → polyester" or truncated)
2. Translation Consistency Value: Would a glossary entry enforce anything a translator wouldn't already do? (5=high enforcement value, 1=obvious translation everyone would use)

Also determine:
- Is this a brand name that should be kept verbatim (not translated)?

Verdict rules:
- If translation_pair_validity < 2: verdict = "rejected", rejection_reasons includes "trivial_pair" or "truncated_target"
- If translation_consistency_value < 2: verdict = "rejected", rejection_reasons includes "low_consistency_need"
- If brand verbatim: verdict = "verbatim_entry", rejection_reasons includes "brand_name_verbatim"
- If both scores >= 4: verdict = "approved"
- Otherwise: verdict = "needs_human_review"

You MUST respond with a single JSON object matching this EXACT schema (no markdown fencing, no extra text):

{{
  "verdict": "approved" | "needs_human_review" | "rejected" | "verbatim_entry",
  "confidence": <float 0.0-1.0>,
  "translation_pair_validity": <int 1-5>,
  "translation_consistency_value": <int 1-5>,
  "is_brand_verbatim": <true or false>,
  "rejection_reasons": [<zero or more of: "trivial_pair", "truncated_target", "partial_translation", "garbled_source", "too_generic", "off_domain", "brand_name_verbatim", "low_consistency_need">],
  "notes": "<1-2 sentences explaining the judgment>"
}}

IMPORTANT: Use lowercase values for verdict and rejection_reasons exactly as shown above."""


USER_PROMPT_PHASE1 = """Judge this source term:

Source term: "{source_term}"
Frequency across products: {frequency}
Fields found in: {field_origins}
"""

USER_PROMPT_PHASE2 = """Judge this translation pair:

Source term: "{source_term}"
Target term: "{target_term}"
Source locale: {source_locale}
Target locale: {target_locale}
Field: {field_origin}
Frequency: {frequency}
LaBSE similarity score: {labse_score:.3f}
"""


# Domain context definitions (customer-specific; only this changes per deployment)
DOMAIN_CONTEXTS = {
    "kappahl": "fashion apparel retail, Scandinavian market, sustainability-focused clothing brand",
}

DEFAULT_DOMAIN_CONTEXT = DOMAIN_CONTEXTS["kappahl"]


def build_system_prompt_phase1(
    domain_context: str = DEFAULT_DOMAIN_CONTEXT,
    source_locale: str = "en",
) -> str:
    return SYSTEM_PROMPT_PHASE1.format(
        domain_context=domain_context,
        source_locale=source_locale,
    )


def build_system_prompt_phase2(
    domain_context: str = DEFAULT_DOMAIN_CONTEXT,
    source_locale: str = "en",
    target_locale: str = "sv-SE",
    field_origin: str = "ProductDescription",
    cross_locale_context: str = "No cross-locale data available.",
) -> str:
    return SYSTEM_PROMPT_PHASE2.format(
        domain_context=domain_context,
        source_locale=source_locale,
        target_locale=target_locale,
        field_origin=field_origin,
        cross_locale_context=cross_locale_context,
    )


def build_user_prompt_phase1(
    source_term: str,
    frequency: int,
    field_origins: str,
) -> str:
    return USER_PROMPT_PHASE1.format(
        source_term=source_term,
        frequency=frequency,
        field_origins=field_origins,
    )


def build_user_prompt_phase2(
    source_term: str,
    target_term: str,
    source_locale: str,
    target_locale: str,
    field_origin: str,
    frequency: int,
    labse_score: float,
) -> str:
    return USER_PROMPT_PHASE2.format(
        source_term=source_term,
        target_term=target_term,
        source_locale=source_locale,
        target_locale=target_locale,
        field_origin=field_origin,
        frequency=frequency,
        labse_score=labse_score,
    )
