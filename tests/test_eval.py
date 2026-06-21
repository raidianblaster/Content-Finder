"""Tests for the eval harness (Milestone 1). Pure, deterministic, no network."""
import os, sys, math, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import eval as E  # noqa: E402

GOLD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evals", "gold.jsonl")


# ---- gold set ----
def test_gold_loads_and_is_wellformed():
    gold = E.load_gold(GOLD)
    assert len(gold) >= 30
    verdicts = {g["expected_verdict"] for g in gold}
    assert verdicts == {"keep", "drop"}
    assert all(g["id"] and g["title"] for g in gold)
    # both classes represented (need negatives to measure precision)
    assert any(g["expected_verdict"] == "drop" for g in gold)
    assert any(g["expected_verdict"] == "keep" for g in gold)


# ---- spearman ----
def test_spearman_identical_is_one():
    assert abs(E.spearman([1, 2, 3, 4], [1, 2, 3, 4]) - 1.0) < 1e-9

def test_spearman_reversed_is_minus_one():
    assert abs(E.spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1.0) < 1e-9

def test_spearman_constant_series_is_zero():
    assert E.spearman([5, 5, 5], [1, 2, 3]) == 0.0

def test_spearman_handles_ties():
    rho = E.spearman([1, 1, 2, 3], [1, 1, 2, 3])
    assert abs(rho - 1.0) < 1e-9


# ---- tag prf ----
def test_tag_prf_perfect():
    p, r, f = E.tag_prf(["Models", "Agents"], ["Agents", "Models"])
    assert (p, r, f) == (1.0, 1.0, 1.0)

def test_tag_prf_partial():
    # expected {Models,Agents,Tooling}; predicted {Models,Agents,Regulation}
    p, r, f = E.tag_prf(["Models", "Agents", "Tooling"], ["Models", "Agents", "Regulation"])
    assert abs(p - 2/3) < 1e-9
    assert abs(r - 2/3) < 1e-9
    assert abs(f - 2/3) < 1e-9

def test_tag_prf_empty_both():
    assert E.tag_prf([], []) == (1.0, 1.0, 1.0)


# ---- verdict metrics ----
def test_verdict_metrics_perfect():
    pairs = [("keep", "keep"), ("drop", "drop"), ("keep", "keep")]
    m = E.verdict_metrics(pairs)
    assert m["accuracy"] == 1.0 and m["precision"] == 1.0 and m["recall"] == 1.0

def test_verdict_metrics_counts_and_f1():
    pairs = [("keep", "keep"), ("keep", "drop"), ("drop", "keep"), ("drop", "drop")]
    m = E.verdict_metrics(pairs)
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == 0.5 and m["recall"] == 0.5
    assert abs(m["f1"] - 0.5) < 1e-9
    assert m["accuracy"] == 0.5


# ---- dedup ----
def test_dedup_pr_perfect():
    p, r = E.dedup_pr([("a", "b")], [("b", "a")])
    assert (p, r) == (1.0, 1.0)

def test_dedup_pr_partial():
    pred = [("a", "b"), ("c", "d")]
    gold = [("a", "b"), ("e", "f")]
    p, r = E.dedup_pr(pred, gold)
    assert p == 0.5 and r == 0.5


# ---- judge variance (M1.2) ----
def test_judge_variance_zero_when_constant():
    v = E.judge_variance([4.0, 4.0, 4.0])
    assert v["stdev"] == 0.0 and v["cv"] == 0.0 and v["half_range"] == 0.0 and v["n"] == 3

def test_judge_variance_reports_spread():
    v = E.judge_variance([3.0, 5.0])
    assert v["mean"] == 4.0
    assert v["half_range"] == 1.0
    assert v["cv"] > 0.0

def test_judge_variance_empty():
    v = E.judge_variance([])
    assert v["n"] == 0


# ---- promotion gate ----
def test_stable_enough_rejects_inside_noise():
    # delta 0.3 with judge stdev 0.5 -> 2*0.5=1.0 band -> not stable
    assert E.stable_enough(0.3, 0.5) is False

def test_stable_enough_accepts_outside_noise():
    assert E.stable_enough(1.5, 0.5) is True


if __name__ == "__main__":
    # dependency-free runner so this validates even without pytest installed
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed")
