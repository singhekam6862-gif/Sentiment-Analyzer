import json

import httpx
import pytest

from app.nlp import opinions
from app.nlp.analysis import analyse, build_aspects
from app.nlp.summarizer import generate_use_cases
from app.schemas import Product, RawReview


def review(rid: str, text: str, rating: int = 4) -> RawReview:
    return RawReview(review_id=rid, product_query="phone", rating=rating, text=text, review_date="2026-09-01",
                     verified_purchase=True)


PHONE = [
    review("p1", "Camera is mast in daylight but battery drains by evening.", 3),
    review("p2", "Display is bahut sharp. Camera is decent.", 5),
    review("p3", "After 2 months the speaker stopped working.", 1),
]

OPINIONS = {
    "p1": [{"aspect": "Camera", "polarity": "praise", "quote": "Camera is mast in daylight"},
           {"aspect": "battery_life", "polarity": "complaint", "quote": "battery drains by evening"}],
    "p2": [{"aspect": "display", "polarity": "praise", "quote": "Display is bahut sharp"},
           {"aspect": "camera", "polarity": "mixed", "quote": "Camera is decent"}],
    "p3": [{"aspect": "long_term_reliability", "polarity": "complaint", "quote": "After 2 months the speaker stopped working"}],
}


def answer_for(prompt: str, table: dict = OPINIONS) -> dict:
    """Answers only for the review ids present in this batch's prompt."""
    return {"reviews": [{"id": rid, "opinions": ops} for rid, ops in table.items() if f"[{rid}]" in prompt]}


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")


def test_parse_keeps_only_verbatim_valid_units():
    batch = {r.review_id: r for r in PHONE[:1]}
    raw = json.dumps({"reviews": [
        {"id": "p1", "opinions": [
            {"aspect": "Camera ", "polarity": "praise", "quote": "“Camera is mast in daylight”"},
            {"aspect": "camera", "polarity": "complaint", "quote": "battery drains by evening"},  # duplicate aspect
            {"aspect": "battery_life", "polarity": "complaint", "quote": "battery dies by night"},  # not verbatim
            {"aspect": "charging", "polarity": "angry", "quote": "battery drains by evening"},  # bad polarity
        ]},
        {"id": "unknown", "opinions": [{"aspect": "x", "polarity": "praise", "quote": "y"}]},
    ]})
    assert opinions.parse_opinions(raw, batch) == {"p1": [("camera", "praise", "Camera is mast in daylight")]}


@pytest.mark.parametrize("raw", ["{broken", json.dumps({"opinions": []}), json.dumps({"reviews": "x"})])
def test_parse_rejects_malformed_answers(raw):
    assert opinions.parse_opinions(raw, {r.review_id: r for r in PHONE}) is None


def test_without_keys_uses_rules_and_no_network(fake_llm):
    fake = fake_llm({"groq": {}})
    found = opinions.extract_all_opinions(PHONE, ["long_term_reliability"])
    assert fake.calls == []
    assert ("long_term_reliability", "complaint", "After 2 months the speaker stopped working") in found["p3"]


def test_rules_skip_earbud_aspects_on_other_products(fake_llm):
    """A geyser review about customer care calls must not become a 'Calls and mic' opinion."""
    fake_llm({"groq": {}})
    geyser = [review("g1", "Great value for money. Customer care calling was very smooth.", 5)]
    found = opinions.extract_all_opinions(geyser, ["long_term_reliability"])
    assert [key for key, _, _ in found["g1"]] == ["value_for_money"]


def test_llm_units_are_used_and_keys_carry_to_later_batches(keys, fake_llm, monkeypatch):
    monkeypatch.setattr(opinions, "BATCH_SIZE", 2)
    fake = fake_llm(lambda _provider, body: answer_for(body["messages"][1]["content"]))

    found = opinions.extract_all_opinions(PHONE, ["long_term_reliability"])

    assert len(fake.calls) == 2
    assert found["p2"] == [("display", "praise", "Display is bahut sharp"), ("camera", "mixed", "Camera is decent")]
    second_prompt = fake.calls[1][1]["messages"][1]["content"]
    assert "camera" in second_prompt.splitlines()[0] and "display" in second_prompt.splitlines()[0]


def test_a_failed_provider_is_not_retried_for_later_batches(keys, fake_llm, monkeypatch):
    """A provider that fails batch 1 (e.g. a timeout) is skipped for batch 2, so it costs one timeout per job."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setattr(opinions, "BATCH_SIZE", 2)
    answers = lambda provider, body: httpx.ReadTimeout("slow") if provider == "groq" else answer_for(body["messages"][1]["content"])
    fake = fake_llm(answers)
    seen: list[str] = []

    found = opinions.extract_all_opinions(PHONE, [], seen.append)

    assert [p for p, _ in fake.calls] == ["groq", "gemini", "gemini"]
    assert found["p3"] == [("long_term_reliability", "complaint", "After 2 months the speaker stopped working")]
    assert seen == ["Reading reviews (part 1 of 2)", "Reading reviews (part 2 of 2)"]


def test_requests_ask_for_low_reasoning_effort(keys, fake_llm):
    """Default reasoning made gpt-oss fail JSON mode on Groq (400 json_validate_failed)."""
    fake = fake_llm(lambda _provider, body: answer_for(body["messages"][1]["content"]))
    opinions.extract_all_opinions(PHONE, [])
    assert fake.calls[0][1]["reasoning_effort"] == "low"


def test_flipkart_aspect_names_are_suggested_to_the_llm(keys, fake_llm):
    fake = fake_llm(lambda _provider, body: answer_for(body["messages"][1]["content"]))
    product = Product(id="p", name="Acme Phone 5G", category="Flipkart product", source_url=None, images=[], specs=[],
                      data_source="live_scrape", collected_on=None)
    analyse(product, PHONE, aspect_hints=["camera", "long_term_reliability"])
    first_line = fake.calls[0][1]["messages"][1]["content"].splitlines()[0]
    assert first_line == "Suggested aspect keys: long_term_reliability, camera"  # template first, no duplicates


def test_a_failed_batch_falls_back_to_rules(keys, fake_llm):
    fake_llm({"groq": "not json"})
    found = opinions.extract_all_opinions(PHONE, [])
    assert found["p3"] == opinions.extract_opinions(PHONE[2])


def test_any_category_gets_its_own_aspects(keys, fake_llm):
    """A phone has no template: aspects come from the LLM, quotes stay verbatim; no use-case answer means none shown."""
    def answer(_provider, body):
        if "opinion units" in body["messages"][0]["content"]:
            return answer_for(body["messages"][1]["content"])
        return {"headline": "Sharp screen, weak battery.", "pros": [{"text": "Sharp display", "aspect": "display"}], "cons": []}

    fake_llm(answer)
    product = Product(id="p", name="Acme Phone 5G", category="Smartphones", source_url=None, images=[], specs=[],
                      data_source="catalogue", collected_on=None)
    result = analyse(product, PHONE)

    labels = {a.key: a.label for a in result.aspects}
    assert labels["camera"] == "Camera" and labels["display"] == "Display"
    assert result.use_cases == []
    texts = {r.review_id: r.text for r in result.reviews}
    assert all(q.text in texts[q.review_id] for a in result.aspects for q in a.quotes)
    assert result.verdict.generated_by == "groq"
    assert result.pros[0].review_ids == ["p2"]


TWO_MENTIONS = [
    review("p1", "Camera is mast in daylight.", 5),
    review("p2", "Camera is great at night.", 5),
    review("p3", "Battery drains by evening.", 2),
    review("p4", "Battery is weak, dies fast.", 2),
    review("p5", "Display is sharp.", 5),
]
TWO_MENTION_OPINIONS = {
    "p1": [{"aspect": "camera", "polarity": "praise", "quote": "Camera is mast in daylight"}],
    "p2": [{"aspect": "camera", "polarity": "praise", "quote": "Camera is great at night"}],
    "p3": [{"aspect": "battery_life", "polarity": "complaint", "quote": "Battery drains by evening"}],
    "p4": [{"aspect": "battery_life", "polarity": "complaint", "quote": "Battery is weak"}],
    "p5": [{"aspect": "display", "polarity": "praise", "quote": "Display is sharp"}],
}


def _product(name: str = "Acme Phone 5G") -> Product:
    return Product(id="p", name=name, category="Flipkart product", source_url=None, images=[], specs=[],
                   data_source="live_scrape", collected_on=None)


def _analysis_answers(use_cases, table=TWO_MENTION_OPINIONS):
    """Routes each LLM call by its system prompt; `use_cases` answers the use-case call."""
    def answer(_provider, body):
        system, prompt = body["messages"][0]["content"], body["messages"][1]["content"]
        if "opinion units" in system:
            return answer_for(prompt, table)
        return use_cases if "use_cases" in system else {"headline": "Fine.", "pros": [], "cons": []}
    return answer


def _use_case_calls(fake) -> list[str]:
    return [body["messages"][1]["content"] for _, body in fake.calls if "use_cases" in body["messages"][0]["content"]]


def test_new_category_gets_use_cases_with_verdicts_from_counts(keys, fake_llm):
    fake = fake_llm(_analysis_answers({"use_cases": [
        {"name": "Photography", "aspect": "camera"}, {"name": "Long days out", "aspect": "battery_life"},
    ]}))

    result = analyse(_product(), TWO_MENTIONS)

    assert {u.name: u.verdict for u in result.use_cases} == {"Photography": "good", "Long days out": "poor"}
    assert {u.name: u.review_count for u in result.use_cases} == {"Photography": 2, "Long days out": 2}
    prompt = _use_case_calls(fake)[0]
    assert "camera" in prompt and "display" not in prompt  # one mention is too few to judge


def test_use_cases_drop_invented_aspects_duplicates_and_bad_names(keys, fake_llm):
    fake_llm(_analysis_answers({"use_cases": [
        {"name": "Photography", "aspect": "camera"},
        {"name": "Gaming", "aspect": "performance"},  # no such aspect in the reviews
        {"name": "Selfies", "aspect": "camera"},  # aspect already used
        {"name": "photography", "aspect": "battery_life"},  # name already used
        {"name": "x" * 41, "aspect": "battery_life"},  # too long for a card
        {"name": None, "aspect": "battery_life"},
    ]}))
    assert [u.name for u in analyse(_product(), TWO_MENTIONS).use_cases] == ["Photography"]


def test_use_cases_stop_at_six(keys, fake_llm):
    fake_llm({"groq": {"use_cases": [{"name": f"Use {i}", "aspect": f"a{i}"} for i in range(7)]}})
    votes = {f"a{i}": [("x", "praise", "good"), ("y", "praise", "good")] for i in range(7)}
    assert len(generate_use_cases("Acme", build_aspects(votes))) == 6


@pytest.mark.parametrize("answer", ["{broken", {"use_cases": "x"}, {"use_cases": []}, {"other": 1}, ["x"]])
def test_bad_use_case_answers_mean_no_section(keys, fake_llm, answer):
    fake_llm(_analysis_answers(answer))
    assert analyse(_product(), TWO_MENTIONS).use_cases == []


def test_without_keys_new_category_has_no_use_cases(fake_llm):
    fake = fake_llm({"groq": {}})
    assert analyse(_product(), TWO_MENTIONS).use_cases == []
    assert fake.calls == []


def test_no_call_when_no_aspect_has_two_mentions(keys, fake_llm):
    table = {"p5": TWO_MENTION_OPINIONS["p5"]}
    fake = fake_llm(_analysis_answers({"use_cases": [{"name": "Viewing", "aspect": "display"}]}, table))
    assert analyse(_product(), TWO_MENTIONS).use_cases == []
    assert _use_case_calls(fake) == []


def test_earbuds_keep_their_template_and_skip_the_call(keys, fake_llm):
    table = {"p1": [{"aspect": "sound_quality", "polarity": "praise", "quote": "Camera is mast in daylight"}],
             "p2": [{"aspect": "sound_quality", "polarity": "praise", "quote": "Camera is great at night"}]}
    fake = fake_llm(_analysis_answers({"use_cases": [{"name": "Nope", "aspect": "sound_quality"}]}, table))

    result = analyse(_product("Acme Buds Pro"), TWO_MENTIONS)

    assert [u.name for u in result.use_cases][:2] == ["Music", "Commuting"]
    assert _use_case_calls(fake) == []
