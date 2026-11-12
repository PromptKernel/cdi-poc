"""Render out/eval/summary.md from the summary dict. Every number carries the label the run computed from the synthetic flag."""
from __future__ import annotations
from . import metrics as M



def _fmt(m):
    return f"{M.pct(m['recall'])} ({m['tp']}/{m['ground_truth']})" if m["ground_truth"] else "n/a (empty ground truth)"


def render(s) -> str:
    meta, L = s["meta"], []
    CAP = s.get("cap", "(measured on synthetic data)")
    a = L.append
    a("# Evaluation summary"); a("")
    a(f"> **{s['label']}**")
    a("> Scenarios and ground truth are written by the repository's author. Nothing here is compared with any outside target.")
    a("")
    gt = meta["ground_truth"]
    a("## Run")
    a(f"- Ground truth: `{gt['file']}` committed as `{gt['commit'][:8]}` at {gt['committed_at']} (before this run; the harness refuses to run otherwise)")
    a(f"- Repository HEAD `{meta['source_head'][:8]}`; baseline: {meta['baseline']}, commits {{{', '.join(f'{r} {c[:8]}' for r, c in meta['baseline_commits'].items())}}}")
    a(f"- Workflow = a graph node of kind {', '.join(meta['workflow_kinds'])} ({meta['universe_workflows']} such workflows in the baseline graph)")
    a(f"- Run at {meta['run_at']}; wall clock {meta['wall_clock_s']} s")
    a("")
    a(f"## Per scenario {CAP}")
    a("")
    a("| Scenario | Ground truth | Reported | Recall (any confidence) | Recall (confirmed links only) | False-positive share | False-positive rate | Unresolved / not found reported | PR run (s) | Baseline |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for p in s["scenarios"]:
        m, c, u = p["metrics_any_confidence"], p["metrics_confirmed_only"], p["unresolved_and_not_found"]
        a(f"| `{p['scenario']}` | {m['ground_truth']} | {m['reported']} | {_fmt(m)} | {_fmt(c)} | {M.pct(m['false_positive_share'])} ({m['fp']}/{m['reported']}) | "
          f"{M.pct(m['false_positive_rate'], 1)} | {u['unresolved_items']} / {u['not_found_items']} | {p['pr_run_duration_s']} | {p['baseline_freshness']['status']} |")
    a("")
    for label, key in (("any confidence", "overall_any_confidence"), ("confirmed links only", "overall_confirmed_only")):
        o = s[key]
        a(f"## Overall, {label} {CAP}")
        a(f"- scenarios: {o['scenarios']} ({o['scenarios_with_empty_ground_truth']} with empty ground truth); ground-truth workflows: {o['ground_truth']}; reported: {o['reported']}; "
          f"true positives {o['tp']}, misses {o['fn']}, unexpected {o['fp']}")
        a(f"- recall: micro {M.pct(o['micro_recall'])} (pooled), macro {M.pct(o['macro_recall'])} (mean over scenarios that have ground truth)")
        a(f"- false-positive share {M.pct(o['micro_false_positive_share'])} (unexpected / reported); false-positive rate {M.pct(o['micro_false_positive_rate'], 1)} (unexpected / workflows that should not be flagged)")
        a("")
    nf = s.get("not_flagged_check")
    if nf is not None:
        a(f"## Check on the 'should NOT be flagged' lists {CAP}")
        a("Separate from the metrics above: these are workflows the author named as not affected. A violation is one of them reported anyway (any confidence).")
        if nf["listed"]:
            a(f"- listed: {nf['listed']} workflow(s) in {nf['scenarios_with_a_list']} scenario(s); reported anyway: {nf['violations']} ({M.pct(nf['violation_rate'], 1)}); "
              f"reported anyway through confirmed links only: {nf['violations_confirmed_only']} ({M.pct(nf['violation_rate_confirmed_only'], 1)})")
        else:
            a("- no scenario lists a workflow that should not be flagged: nothing to check.")
        for p in s["scenarios"]:
            c = p.get("not_flagged_check")
            for d in (c or {}).get("detail", []):
                dd = "; ".join(f"via `{x['via']}` [{x['confidence']}]" + (f" at {x['evidence']}" if x.get("evidence") else "") for x in d["detail"])
                a(f"- violation: `{p['scenario']}` / `{d['workflow']}` - {dd}")
        a("")
    t = s["timing"]
    a(f"## Timing {CAP}")
    a(f"- baseline build: {t['baseline_build_s']} s; PR run: mean {t['pr_run_mean_s']} s, max {t['pr_run_max_s']} s (one repository, one machine)")
    a("")
    a(f"## Misses: ground-truth workflows the tool did not report, and why {CAP}")
    any_ = False
    for p in s["scenarios"]:
        for m in p["misses"]:
            any_ = True
            a(f"- `{p['scenario']}` / `{m['workflow']}` - **{m['code']}**: {m['reason']}")
    if not any_:
        a("_None._")
    a("")
    a(f"## Found only through INFERRED links {CAP}")
    inf = [(p["scenario"], w) for p in s["scenarios"] for w in p["found_only_through_inferred_links"]]
    a("\n".join(f"- `{sc}` / `{w}`" for sc, w in inf) if inf else "_None._")
    a("")
    a(f"## Unexpected workflows (reported, not in the ground truth) {CAP}")
    any_ = False
    for p in s["scenarios"]:
        for u in p["unexpected"]:
            any_ = True
            d = "; ".join(f"via `{x['via']}` [{x['confidence']}]" + (f" at {x['evidence']}" if x.get("evidence") else "") for x in u["detail"])
            a(f"- `{p['scenario']}` / `{u['workflow']}` - {d}")
    if not any_:
        a("_None._")
    a("")
    a("## Method and limits")
    a("See `docs/evaluation.md`. Author-written scenarios and ground truth: these numbers describe how the tool behaves on this repository's scenarios, not on other code.")
    return "\n".join(L) + "\n"
