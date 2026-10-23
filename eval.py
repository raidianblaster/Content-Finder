#!/usr/bin/env python3
"""Content-Finder eval harness (Milestone 1).

A dependency-free ruler for the pipeline. Pure, deterministic scoring functions
(unit-tested in tests/test_eval.py) plus a CLI that scores the pipeline against a
frozen gold set (evals/gold.jsonl) and prints a baseline report.

Includes Milestone 1.2 — judge-reliability instrumentation: because LLM-as-judge
scores have been shown to carry coin-flip-level variance, every judge-backed
number is reported WITH its own variance, and a promotion gate refuses deltas
that sit inside the judge's noise band.

Design intent (see ROADMAP-vNext.md, Phase 1):
  * 1.1 reference-based eval over a frozen gold set
  * 1.2 judge-variance instrumentation (this module's `judge_variance`/`stable_enough`)
  * 1.3 cross-config evaluation (run the same gold set across scaffold variants)

No third-party deps (no numpy/scipy) — keeps the key-free path and CI light.
"""
from __future__ import annotations
import json, math, argparse, statistics
from typing import Iterable, Sequence


# ----------------------------------------------------------------- gold set
def load_gold(path: str) -> list[dict]:
    """Load the frozen gold set (JSONL). Skips blank lines."""
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


# ----------------------------------------------------------------- ranking
def _ranks(xs: Sequence[float]) -> list[float]:
    """Average ranks (1-based), ties share the mean rank."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman rank correlation. Returns 1.0 for identical orderings,
    0.0 for a constant series (no information)."""
    if len(a) != len(b):
        raise ValueError("series length mismatch")
    n = len(a)
    if n < 2:
        return 0.0
    ra, rb = _ranks(a), _ranks(b)
    mra, mrb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - mra) * (rb[i] - mrb) for i in range(n))
    da = math.sqrt(sum((r - mra) ** 2 for r in ra))
    db = math.sqrt(sum((r - mrb) ** 2 for r in rb))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


# ----------------------------------------------------------------- tags
def tag_prf(expected: Iterable[str], predicted: Iterable[str]) -> tuple[float, float, float]:
    """Precision, recall, F1 over a tag set (order-insensitive)."""
    e, p = set(expected), set(predicted)
    if not e and not p:
        return 1.0, 1.0, 1.0
    tp = len(e & p)
    precision = tp / len(p) if p else 0.0
    recall = tp / len(e) if e else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


# ----------------------------------------------------------------- verdicts
def verdict_metrics(pairs: Sequence[tuple[str, str]]) -> dict:
    """pairs of (expected, predicted) in {'keep','drop'}.
    Treats 'keep' as the positive class."""
    tp = fp = tn = fn = 0
    for exp, pred in pairs:
        if exp == "keep" and pred == "keep": tp += 1
        elif exp == "drop" and pred == "keep": fp += 1
        elif exp == "drop" and pred == "drop": tn += 1
        elif exp == "keep" and pred == "drop": fn += 1
    total = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    accuracy = (tp + tn) / total if total else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "accuracy": accuracy,
            "f1": f1, "tp": tp, "fp": fp, "tn": tn, "fn": fn}


# ----------------------------------------------------------------- dedup
def dedup_pr(predicted_pairs: Iterable[frozenset], gold_pairs: Iterable[frozenset]) -> tuple[float, float]:
    """Precision/recall of duplicate detection over unordered id-pairs."""
    pred = {frozenset(p) for p in predicted_pairs}
    gold = {frozenset(p) for p in gold_pairs}
    if not pred and not gold:
        return 1.0, 1.0
    tp = len(pred & gold)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(gold) if gold else 0.0
    return precision, recall


# ----------------------------------------------------------------- judge variance (M1.2)
def judge_variance(scores: Sequence[float]) -> dict:
    """Instrument an LLM-as-judge's reliability: run the judge k times on the
    same input and summarise the spread. `cv` (coefficient of variation) is the
    headline noise number; `half_range` bounds a single reading's wobble."""
    n = len(scores)
    if n == 0:
        return {"n": 0, "mean": 0.0, "stdev": 0.0, "cv": 0.0, "half_range": 0.0}
    mean = sum(scores) / n
    stdev = statistics.stdev(scores) if n > 1 else 0.0
    cv = (stdev / mean) if mean else 0.0
    half_range = (max(scores) - min(scores)) / 2.0
    return {"n": n, "mean": mean, "stdev": stdev, "cv": cv, "half_range": half_range}


def stable_enough(delta: float, judge_noise_stdev: float, k: float = 2.0) -> bool:
    """Promotion gate: an eval delta is only trustworthy if it exceeds the
    judge's own noise band (default: k=2 standard deviations)."""
    return abs(delta) > k * judge_noise_stdev


# ----------------------------------------------------------------- CLI
def _baseline_report(gold_path: str) -> dict:
    gold = load_gold(gold_path)
    keep = sum(1 for g in gold if g.get("expected_verdict") == "keep")
    drop = sum(1 for g in gold if g.get("expected_verdict") == "drop")
    tagged = sum(1 for g in gold if g.get("expected_tags"))
    return {"gold_items": len(gold), "keep": keep, "drop": drop, "with_tags": tagged}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Content-Finder eval harness")
    ap.add_argument("--gold", default="evals/gold.jsonl")
    ap.add_argument("--judge-runs", type=int, default=0,
                    help="(M1.2) intended #judge repetitions for variance instrumentation")
    args = ap.parse_args(argv)
    rep = _baseline_report(args.gold)
    print("Content-Finder eval — gold-set summary")
    print(f"  items: {rep['gold_items']}  (keep={rep['keep']}, drop={rep['drop']}, tagged={rep['with_tags']})")
    print("  pipeline integration: wire score_item / tag-assignment / dedup outputs here,")
    print("  then compare against the gold labels with the functions in this module.")
    if args.judge_runs:
        print(f"  judge-variance mode: re-run the LLM judge x{args.judge_runs} per item; "
              "report cv and gate promotions with stable_enough().")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
