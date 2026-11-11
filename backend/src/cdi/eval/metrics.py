"""Metric calculations for the evaluation harness. Pure functions over sets of workflow names.
ALL numbers produced from them are 'measured on synthetic data' (the synthetic-extended sample); they say nothing about real code.

Definitions (per scenario), with GT = ground-truth workflows, R = workflows the tool reported, U = all workflows in the baseline graph:
  TP = GT & R          FN = GT - R (misses)          FP = R - GT (unexpected workflows)
  recall                = |TP| / |GT|                (None when GT is empty: nothing to recall)
  false_positive_share  = |FP| / |R|                 (the share of reported workflows that are not in the ground truth; None when R is empty)
  false_positive_rate   = |FP| / |U - GT|            (the share of workflows that should NOT be flagged but were; None when there are none such)
  precision             = |TP| / |R|                 (None when R is empty)
"""
from __future__ import annotations


def _ratio(n: int, d: int):
    return (n / d) if d else None


def workflow_metrics(gt, reported, universe=None) -> dict:
    gt, reported = set(gt), set(reported)
    tp, fn, fp = gt & reported, gt - reported, reported - gt
    negatives = None if universe is None else set(universe) - gt
    return {
        "ground_truth": len(gt), "reported": len(reported), "tp": len(tp), "fn": len(fn), "fp": len(fp),
        "recall": _ratio(len(tp), len(gt)),
        "precision": _ratio(len(tp), len(reported)),
        "false_positive_share": _ratio(len(fp), len(reported)),
        "false_positive_rate": None if negatives is None else _ratio(len(fp), len(negatives)),
        "negatives": None if negatives is None else len(negatives),
        "true_positives": sorted(tp), "misses": sorted(fn), "unexpected": sorted(fp),
    }


def aggregate(per_scenario) -> dict:
    """per_scenario: list of workflow_metrics dicts.
    micro = pooled counts (every ground-truth workflow weighs the same); macro_recall = mean of per-scenario recalls over scenarios that HAVE ground truth."""
    gt = sum(m["ground_truth"] for m in per_scenario)
    rep = sum(m["reported"] for m in per_scenario)
    tp = sum(m["tp"] for m in per_scenario)
    fp = sum(m["fp"] for m in per_scenario)
    fn = sum(m["fn"] for m in per_scenario)
    neg = [m["negatives"] for m in per_scenario if m.get("negatives") is not None]
    recalls = [m["recall"] for m in per_scenario if m["recall"] is not None]
    return {
        "scenarios": len(per_scenario), "scenarios_with_ground_truth": len(recalls), "scenarios_with_empty_ground_truth": len(per_scenario) - len(recalls),
        "ground_truth": gt, "reported": rep, "tp": tp, "fn": fn, "fp": fp,
        "micro_recall": _ratio(tp, gt),
        "macro_recall": (sum(recalls) / len(recalls)) if recalls else None,
        "micro_false_positive_share": _ratio(fp, rep),
        "micro_false_positive_rate": _ratio(fp, sum(neg)) if neg else None,
    }


def pct(x, digits=0) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"
