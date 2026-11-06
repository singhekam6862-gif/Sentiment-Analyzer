import re

from app.schemas import AspectKey
from app.nlp.preprocessor import normalize_review_text

# Keywords mapping clauses to the 6 core pillars
ASPECT_KEYWORDS: dict[AspectKey, list[str]] = {
    AspectKey.SOUND_QUALITY: [
        "sound", "bass", "treble", "audio", "clarity", "music", "vocal", "vocals",
        "loud", "loudness", "volume", "driver", "drivers", "12.4mm", "eq", "punchy",
        "crisp", "instrument", "acoustic", "hear music"
    ],
    AspectKey.ANC_NOISE_CANCELLATION: [
        "anc", "noise cancellation", "noise cancelling", "transparency", "ambient",
        "outside noise", "background noise", "46db", "traffic noise", "metro",
        "commute noise", "isolation", "active noise"
    ],
    AspectKey.MIC_CALL_QUALITY: [
        "mic", "microphone", "call", "calls", "calling", "voice", "voice quality",
        "speaking", "hear my voice", "traffic road", "outdoors", "zoom", "meeting",
        "other person", "receiver"
    ],
    AspectKey.BATTERY_LIFE: [
        "battery", "backup", "charging", "charge", "charger", "hours", "drain",
        "playtime", "playback", "mah", "case charge", "type-c", "stopped charging"
    ],
    AspectKey.COMFORT_BUILD: [
        "fit", "comfort", "comfortable", "ear pain", "ears", "in ear", "gym",
        "workout", "fall out", "falling", "build", "plastic", "hinge", "case scratches",
        "glossy case", "lid", "lightweight", "design", "durability"
    ],
    AspectKey.VALUE_FOR_MONEY: [
        "paisa vasool", "value", "worth", "price", "budget", "money", "rupee",
        "rupees", "overpriced", "expensive", "cheap", "cost", "deal", "paisa barbaad"
    ],
}

# Logistics & seller complaint cues
LOGISTICS_KEYWORDS: list[str] = [
    "unsealed", "open box", "delivery", "courier", "packaging", "package",
    "missing", "fake seller", "damaged box", "return replacement", "shipping",
    "late delivery", "wrong item", "refund", "seal broken", "crushed box",
    "crushed", "seller service", "ekart", "flipkart delivery", "wrong color", "wrong colour",
    "seller issue", "replacement"
]

POSITIVE_CUES = {
    "excellent", "amazing", "great value for money", "great", "mind-blowing",
    "top notch", "punchy", "crisp", "terrific", "good", "super", "superb",
    "loved", "perfect", "clear", "heavy", "solid", "tight", "remarkably"
}

NEGATIVE_CUES = {
    "terrible", "bakwas", "bekar", "ghatiya", "rubbish", "garbage", "waste of money",
    "scam", "poor", "useless", "cracks", "worst", "bad", "disappointing",
    "scratched", "scratches", "stopped", "drain", "refused", "false", "crushed",
    "broken", "damage", "delicate", "sensitive", "complain", "artificial", "robotic", "dropped"
}

NEGATION_CUES = {"not", "never", "no", "nahi", "mat", "definitely not", "hardly", "barely"}


def is_logistics_complaint(text: str, rating: int) -> bool:
    """Detects if a negative review is primarily about seller/delivery/logistics."""
    lower = text.lower()
    has_logistics = any(k in lower for k in LOGISTICS_KEYWORDS)
    return has_logistics and (rating <= 2 or any(neg in lower for neg in ["terrible", "poor", "crushed", "missing", "broken"]))


def split_into_clauses(text: str) -> list[str]:
    """Splits review into clauses using punctuation and contrasting conjunctions."""
    # Split on periods, exclamation marks, semicolons, and conjunctions like but, lekin, par, however
    # Punctuation only ends a clause before whitespace/end, so "2.5k" and "1.5 hours" stay whole.
    pattern = r"[.!?;]+(?=\s|$)|\b(?:but|lekin|par|however|though|while|although)\b"
    raw_clauses = re.split(pattern, text, flags=re.IGNORECASE)
    clauses = [c.strip() for c in raw_clauses if len(c.strip()) > 3]
    return clauses if clauses else [text.strip()]


def score_clause_sentiment(clause: str, review_rating: int) -> float:
    """Scores a clause from 0 to 100 based on lexicon sentiment and rating."""
    tokens = [t.strip(",").lower() for t in clause.split()]
    net_score = 0
    i = 0

    while i < len(tokens):
        word = tokens[i]
        # Check window for negation (preceding or succeeding for Hinglish)
        is_negated = False
        for back in range(max(0, i - 3), i):
            if tokens[back] in NEGATION_CUES:
                is_negated = True
                break
        if not is_negated:
            for fwd in range(i + 1, min(len(tokens), i + 3)):
                if tokens[fwd] in NEGATION_CUES:
                    is_negated = True
                    break

        if any(pos in word for pos in POSITIVE_CUES):
            net_score += -1 if is_negated else 1
        elif any(neg in word for neg in NEGATIVE_CUES):
            net_score += 1 if is_negated else -1
        i += 1

    if net_score > 0:
        return 88.0
    elif net_score < 0:
        return 22.0
    else:
        # Default fallback to review rating (1->25, 2->40, 3->50, 4->72, 5->88)
        rating_map = {1: 25.0, 2: 40.0, 3: 50.0, 4: 72.0, 5: 88.0}
        return rating_map.get(review_rating, 50.0)


def extract_aspects_from_clause(clause: str) -> list[AspectKey]:
    """Detects which of the 6 pillars are mentioned in this clause."""
    lower = clause.lower()
    detected = []
    for aspect, keywords in ASPECT_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(k)}\b", lower) for k in keywords):
            detected.append(aspect)
    return detected


def classify_review_sentiment(text: str, rating: int) -> str:
    """Classifies overall review sentiment into positive, negative, or neutral."""
    norm = normalize_review_text(text)
    cleaned = norm["cleaned_text"].lower()

    # Calculate net tokens
    clauses = split_into_clauses(cleaned)
    clause_scores = [score_clause_sentiment(c, rating) for c in clauses]
    avg_score = sum(clause_scores) / len(clause_scores) if clause_scores else 50.0

    if rating >= 4:
        return "negative" if avg_score < 35 else "positive"
    elif rating <= 2:
        return "positive" if avg_score > 70 else "negative"
    # 3★: averaging lets cue-less clauses (score 50) tip a balanced review, so compare praise and complaints directly
    has_praise, has_complaint = any(s > 50 for s in clause_scores), any(s < 50 for s in clause_scores)
    if has_praise == has_complaint:
        return "neutral"
    return "positive" if has_praise else "negative"
