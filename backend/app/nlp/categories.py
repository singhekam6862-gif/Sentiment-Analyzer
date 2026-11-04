"""Aspect labels and per-category use-case templates (SPEC §A.5, §A.6)."""

RELIABILITY = "long_term_reliability"

LABELS = {
    "sound_quality": "Sound quality",
    "anc_noise_cancellation": "Noise cancelling",
    "mic_call_quality": "Calls and mic",
    "battery_life": "Battery life",
    "comfort_build": "Comfort and build",
    "value_for_money": "Value for money",
    RELIABILITY: "Long-term reliability",
}

# use case name -> aspect keys it is judged on
EARBUDS = [
    ("Music", ["sound_quality"]),
    ("Commuting", ["anc_noise_cancellation"]),
    ("Gym and running", ["comfort_build"]),
    ("Office calls", ["mic_call_quality"]),
    ("Lasting a year", [RELIABILITY]),
]


def label(key: str) -> str:
    return LABELS.get(key, key.replace("_", " ").capitalize())


def use_case_template(name: str, category: str) -> list[tuple[str, list[str]]]:
    """Use cases for the product's category; empty when no template fits."""
    text = f"{name} {category}".lower()
    return EARBUDS if any(w in text for w in ("earbud", "buds", "tws", "headphone", "earphone")) else []


def suggested_aspects(name: str, category: str) -> list[str]:
    """Aspect keys offered to the LLM so its keys line up with the template's use cases."""
    return list(LABELS) if use_case_template(name, category) else [RELIABILITY]
