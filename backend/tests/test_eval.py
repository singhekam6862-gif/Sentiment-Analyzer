import pytest

from app.nlp.categories import LABELS
from eval.__main__ import GROUPS, SENTIMENTS, load_gold, load_reviews, main
from eval.metrics import accuracy, confusion, macro_f1, prf, set_prf


def test_prf_handles_empty_denominators():
    assert prf(0, 0, 0) == (0.0, 0.0, 0.0)
    assert prf(2, 2, 0) == (0.5, 1.0, pytest.approx(2 / 3))


def test_macro_f1_weighs_each_label_equally():
    gold = ["pos", "pos", "pos", "neg"]
    pred = ["pos", "pos", "pos", "pos"]
    # pos: P 0.75, R 1 -> F1 6/7; neg: never predicted -> 0
    assert macro_f1(gold, pred, ["pos", "neg"]) == pytest.approx(3 / 7)
    assert accuracy(gold, pred) == 0.75


def test_confusion_rows_are_gold_columns_are_predicted():
    assert confusion(["a", "a", "b"], ["a", "b", "b"], ["a", "b"]) == [[1, 1], [0, 1]]


def test_set_prf_on_review_aspect_pairs():
    assert set_prf({("r1", "battery"), ("r2", "sound")}, {("r1", "battery"), ("r1", "sound")}) == (0.5, 0.5, 0.5)


def test_gold_set_labels_every_seed_review_with_valid_values():
    gold = load_gold()
    seed_ids = {r.review_id for reviews in load_reviews().values() for r in reviews}
    assert set(gold) == seed_ids
    for row in gold.values():
        assert row["sentiment"] in SENTIMENTS and row["group"] in GROUPS
        assert set(row["aspects"]) <= set(LABELS)
        assert set(row["aspects"].values()) <= {"praise", "complaint", "mixed"}
        assert row["group"] == "product" or not row["aspects"]  # only product reviews carry aspect labels


def test_offline_harness_produces_every_section(tmp_path):
    out = tmp_path / "results.md"
    text = main(["--out", str(out)])
    for heading in ("## Review sentiment", "## Review groups", "## Aspects", "Star rating only (baseline)"):
        assert heading in text
    assert out.read_text(encoding="utf-8").strip() == text.strip()
