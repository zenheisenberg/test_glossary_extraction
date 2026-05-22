"""spaCy Matcher patterns for fashion domain term extraction."""


def get_matcher_patterns():
    """Return patterns for spaCy Matcher.

    Each pattern matches fashion-relevant multi-word terms.
    Pattern format: list of token dicts for spaCy Matcher.
    """
    patterns = {
        # ADJ + NOUN: "organic cotton", "ribbed jersey"
        "ADJ_NOUN": [
            [{"POS": "ADJ"}, {"POS": "NOUN"}],
        ],
        # ADJ + ADJ + NOUN: "soft brushed fleece"
        "ADJ_ADJ_NOUN": [
            [{"POS": "ADJ"}, {"POS": "ADJ"}, {"POS": "NOUN"}],
        ],
        # NOUN + NOUN: "cotton blend", "jersey fabric"
        "NOUN_NOUN": [
            [{"POS": "NOUN"}, {"POS": "NOUN"}],
        ],
        # ADJ + NOUN + NOUN: "recycled polyester fabric"
        "ADJ_NOUN_NOUN": [
            [{"POS": "ADJ"}, {"POS": "NOUN"}, {"POS": "NOUN"}],
        ],
        # FIT patterns: "relaxed fit", "slim fit"
        "FIT_PATTERN": [
            [{"POS": "ADJ"}, {"LOWER": "fit"}],
            [{"POS": "ADJ"}, {"POS": "ADJ"}, {"LOWER": "fit"}],
        ],
        # LEG patterns: "wide leg", "straight leg"
        "LEG_PATTERN": [
            [{"POS": "ADJ"}, {"LOWER": "leg"}],
        ],
        # WAIST patterns: "high waist", "elastic waistband"
        "WAIST_PATTERN": [
            [{"POS": "ADJ"}, {"LOWER": {"IN": ["waist", "waistband"]}}],
        ],
        # CLOSURE patterns: "zip closure", "button closure"
        "CLOSURE_PATTERN": [
            [{"POS": {"IN": ["NOUN", "ADJ"]}}, {"LOWER": "closure"}],
        ],
        # NECK patterns: "crew neck", "round neck"
        "NECK_PATTERN": [
            [{"POS": {"IN": ["NOUN", "ADJ"]}}, {"LOWER": "neck"}],
        ],
        # SLEEVE patterns: "long sleeve", "short sleeve"
        "SLEEVE_PATTERN": [
            [{"POS": "ADJ"}, {"LOWER": {"IN": ["sleeve", "sleeved"]}}],
        ],
    }
    return patterns
