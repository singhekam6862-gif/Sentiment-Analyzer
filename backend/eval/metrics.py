"""Plain classification metrics, so the numbers in the report can be checked by hand."""

from collections.abc import Sequence


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """(precision, recall, F1); 0.0 where the denominator is zero."""
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def accuracy(gold: Sequence[str], pred: Sequence[str]) -> float:
    return sum(g == p for g, p in zip(gold, pred, strict=True)) / len(gold) if gold else 0.0


def macro_f1(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> float:
    """Unweighted mean of per-label F1, so a rare class (neutral, suspicious) counts as much as a common one."""
    scores = []
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, pred, strict=True))
        fp = sum(g != label and p == label for g, p in zip(gold, pred, strict=True))
        fn = sum(g == label and p != label for g, p in zip(gold, pred, strict=True))
        scores.append(prf(tp, fp, fn)[2])
    return sum(scores) / len(scores) if scores else 0.0


def confusion(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> list[list[int]]:
    """rows = gold label, columns = predicted label, in `labels` order."""
    pairs = list(zip(gold, pred, strict=True))
    return [[sum(1 for g, p in pairs if g == row and p == col) for col in labels] for row in labels]


def set_prf(gold: set, pred: set) -> tuple[float, float, float]:
    return prf(len(gold & pred), len(pred - gold), len(gold - pred))
