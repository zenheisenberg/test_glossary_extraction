"""Kappahl Glossary Extraction Pipeline v2 - Configuration"""
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR
EXCEL_PATH = PROJECT_ROOT / ".implementation_files" / "Produkttexter_Kappahl_språk_fält_PIM.xlsx"
DB_PATH = BASE_DIR / "glossary_candidates.db"

# Locales
SOURCE_LOCALE = "en"
TARGET_LOCALES = ["sv-SE", "fi-FI", "de-DE", "nb-NO", "pl-PL"]

# Fields and their weights (higher = more authoritative for terminology)
FIELD_WEIGHTS = {
    "ProductNameShort": 1.0,
    "ProductDescription": 0.8,
    "ProductFeatures": 0.9,
    "ProductSustainableMaterialcomposition": 1.0,
    "ItemNameLong": 0.7,
    "ItemDescription": 0.6,
    "ItemUSP": 0.5,
}

# LaBSE thresholds
LABSE_STRONG = 0.85
LABSE_REVIEW = 0.75
LABSE_REJECT = 0.65

# Scoring weights
SCORING_WEIGHTS = {
    "labse": 0.30,
    "frequency": 0.20,
    "field_weight": 0.15,
    "domain_priority": 0.15,
    "translation_consistency": 0.10,
    "brand_relevance": 0.10,
}

# Extraction constraints
MAX_TERM_WORDS = 6
MIN_TERM_WORDS = 1
MIN_TERM_CHARS = 3

# Blacklisted phrases (marketing fluff)
BLACKLIST = [
    "perfect for",
    "easy to wear",
    "comes with",
    "available in",
    "a great choice",
    "great for",
    "ideal for",
    "suitable for",
    "designed to",
    "made to",
    "look and feel",
    "day to day",
    "everyday wear",
    "all day",
    "must have",
    "go to",
    "on trend",
    "bang on trend",
]

# Fashion compound term normalization rules: (pattern, replacement)
FASHION_COMPOUNDS = [
    (r"\bT\s+shirt", "T-shirt"),
    (r"\bt\s+shirt", "t-shirt"),
    (r"\boff\s+white\b", "off-white"),
    (r"\bwide\s+leg\b", "wide-leg"),
    (r"\b[vV]\s+neck\b", "V-neck"),
    (r"\bcrew\s+neck\b", "crew-neck"),
    (r"\bround\s+neck\b", "round-neck"),
    (r"\bhigh\s+waist\b", "high-waist"),
    (r"\blow\s+rise\b", "low-rise"),
    (r"\bmid\s+rise\b", "mid-rise"),
    (r"\blong\s+sleeve\b", "long-sleeve"),
    (r"\bshort\s+sleeve\b", "short-sleeve"),
    (r"\bdrop\s+shoulder\b", "drop-shoulder"),
    (r"\bA\s+line\b", "A-line"),
    (r"\banti\s+slip\b", "anti-slip"),
]
