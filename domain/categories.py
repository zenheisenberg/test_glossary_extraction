"""Domain category definitions and priority scores for Kappahl fashion terminology."""

# Domain → seed terms (used for PhraseMatcher and classification)
DOMAIN_TERMS = {
    "product_types": [
        "hoodie", "cardigan", "leggings", "sweatshirt", "bodysuit", "jeans",
        "blouse", "jacket", "dress", "trousers", "shorts", "skirt", "coat",
        "parka", "blazer", "vest", "jumpsuit", "romper", "tunic", "polo",
        "tank top", "t-shirt", "shirt", "sweater", "pullover", "joggers",
        "chinos", "dungarees", "kimono", "cape", "poncho",
    ],
    "materials": [
        "organic cotton", "brushed fleece", "ribbed jersey", "recycled polyester",
        "woven fabric", "cotton", "polyester", "viscose", "elastane", "nylon",
        "linen", "wool", "silk", "denim", "jersey", "fleece", "velour",
        "corduroy", "twill", "satin", "chiffon", "mesh", "knit", "terry",
        "lyocell", "tencel", "modal", "cashmere", "merino",
    ],
    "sustainability": [
        "organic cotton", "certified cotton", "recycled material",
        "responsibly sourced cotton", "recycled polyester", "sustainable",
        "eco-friendly", "GOTS certified", "BCI cotton", "organic",
        "recycled", "responsible", "certified",
    ],
    "fit_silhouette": [
        "relaxed fit", "oversized fit", "slim fit", "regular fit",
        "wide leg", "straight leg", "high waist", "low waist",
        "skinny fit", "tapered leg", "flared leg", "bootcut",
        "loose fit", "comfort fit", "athletic fit",
    ],
    "construction": [
        "ribbed cuffs", "drawstring waist", "adjustable straps",
        "zip closure", "elastic waistband", "button closure",
        "snap closure", "velcro closure", "ribbed hem", "flat seams",
        "reinforced knees", "lined", "padded", "quilted",
        "double layered", "turn-up hem", "side pockets",
    ],
    "patterns_appearance": [
        "floral print", "holographic effect", "washed look",
        "embroidered detail", "striped", "checked", "plaid",
        "polka dot", "animal print", "camouflage", "tie-dye",
        "colour block", "graphic print", "sequin", "glitter",
    ],
    "baby_kidswear": [
        "wrap bodysuit", "padded snowsuit", "anti-slip socks",
        "footed sleepsuit", "bib", "romper suit", "crawler",
        "one-piece", "sleep bag", "swaddle",
    ],
    "underwear_nightwear": [
        "wireless bra", "seamless underwear", "pajama set",
        "boxer shorts", "briefs", "nightgown", "dressing gown",
        "sports bra", "bralette", "hipster", "thong",
    ],
}

# Domain priority scores (higher = more important for glossary)
DOMAIN_PRIORITY = {
    "materials": 1.0,
    "sustainability": 1.0,
    "fit_silhouette": 0.9,
    "construction": 0.85,
    "product_types": 0.8,
    "patterns_appearance": 0.7,
    "baby_kidswear": 0.75,
    "underwear_nightwear": 0.75,
    "general": 0.5,
}
