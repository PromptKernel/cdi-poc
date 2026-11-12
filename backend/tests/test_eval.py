"""Evaluation harness: metric calculations (including empty ground truth and extra unexpected workflows), ground-truth conversion/validation/commit guard,
miss explanations, report labelling, and one end-to-end run on a TEST-ONLY fixture ground truth (never the real eval/ground_truth.yml)."""
import json, pathlib, subprocess
import pytest, yaml
from conftest import ROOT, BACKEND, Project, sh, GIT_ID
from cdi.eval import ground_truth as G, metrics as M, report, run_eval as R
from helpers import node, edge, graph


# ------------------------------------------------------------------ metrics
U = {"a", "b", "c", "x", "y", "z"}


def test_metrics_basic_counts_and_ratios():
    m = M.workflow_metrics({"a", "b", "c"}, {"a", "b", "x"}, U)
    assert (m["tp"], m["fn"], m["fp"], m["ground_truth"], m["reported"]) == (2, 1, 1, 3, 3)
    assert m["recall"] == pytest.approx(2 / 3) and m["precision"] == pytest.approx(2 / 3) and m["false_positive_share"] == pytest.approx(1 / 3)
    assert m["negatives"] == 3 and m["false_positive_rate"] == pytest.approx(1 / 3)          # x is the 1 false positive among {x, y, z}
    assert (m["true_positives"], m["misses"], m["unexpected"]) == (["a", "b"], ["c"], ["x"])


def test_metrics_empty_ground_truth_every_reported_workflow_is_unexpected():
    m = M.workflow_metrics(set(), {"x", "y"}, U)
    assert m["recall"] is None and m["tp"] == 0 and m["fn"] == 0 and m["fp"] == 2
    assert m["false_positive_share"] == 1.0 and m["precision"] == 0.0 and m["false_positive_rate"] == pytest.approx(2 / 6)


def test_metrics_empty_ground_truth_and_nothing_reported_is_a_clean_pass_with_undefined_ratios():
    m = M.workflow_metrics(set(), set(), U)
    assert (m["tp"], m["fn"], m["fp"]) == (0, 0, 0)
    assert m["recall"] is None and m["precision"] is None and m["false_positive_share"] is None
    assert m["false_positive_rate"] == 0.0


def test_metrics_nothing_reported_for_nonempty_ground_truth_is_zero_recall():
    m = M.workflow_metrics({"a", "b"}, set(), U)
    assert m["recall"] == 0.0 and m["fn"] == 2 and m["false_positive_share"] is None and m["precision"] is None


def test_metrics_extra_unexpected_workflows_lower_the_false_positive_numbers_not_recall():
    m = M.workflow_metrics({"a"}, {"a", "x", "y", "z"}, U)
    assert m["recall"] == 1.0 and m["fp"] == 3 and m["false_positive_share"] == pytest.approx(3 / 4) and m["false_positive_rate"] == pytest.approx(3 / 5)


def test_metrics_universe_edge_cases():
    assert M.workflow_metrics({"a"}, {"a"}, None)["false_positive_rate"] is None            # no universe given
    assert M.workflow_metrics({"a", "b"}, {"a"}, {"a", "b"})["false_positive_rate"] is None  # every workflow is expected: no negatives to be wrong about
    m = M.workflow_metrics(["a", "a"], ["a", "a"], U)                                         # duplicates collapse
    assert (m["ground_truth"], m["reported"], m["tp"]) == (1, 1, 1)


def test_aggregate_micro_pools_counts_macro_averages_scenarios_with_ground_truth():
    s1 = M.workflow_metrics({"a", "b"}, {"a", "b"}, U)                       # recall 1.0, 2 gt
    s2 = M.workflow_metrics({f"w{i}" for i in range(8)}, {f"w{i}" for i in range(4)} | {"x"}, U | {f"w{i}" for i in range(8)})   # recall 0.5, 8 gt, 1 fp
    s3 = M.workflow_metrics(set(), {"y"}, U)                                  # empty ground truth, 1 fp
    o = M.aggregate([s1, s2, s3])
    assert (o["scenarios"], o["scenarios_with_ground_truth"], o["scenarios_with_empty_ground_truth"]) == (3, 2, 1)
    assert (o["ground_truth"], o["tp"], o["fn"], o["fp"], o["reported"]) == (10, 6, 4, 2, 2 + 5 + 1)
    assert o["micro_recall"] == pytest.approx(0.6) and o["macro_recall"] == pytest.approx(0.75)
    assert o["micro_false_positive_share"] == pytest.approx(2 / 8)


def test_aggregate_edge_cases():
    o = M.aggregate([])
    assert o["scenarios"] == 0 and o["micro_recall"] is None and o["macro_recall"] is None and o["micro_false_positive_share"] is None
    o = M.aggregate([M.workflow_metrics(set(), set(), U)])
    assert o["micro_recall"] is None and o["macro_recall"] is None and o["scenarios_with_empty_ground_truth"] == 1


def test_pct_formatting():
    assert M.pct(None) == "n/a" and M.pct(0.5) == "50%" and M.pct(1 / 3, 1) == "33.3%" and M.pct(0.0) == "0%"


# ------------------------------------------------------------------ reported workflows, unresolved counts
def fake_result():
    cons = lambda name, kind, conf: {"name": name, "kind": kind, "confidence": conf, "path": [{"repo": "web", "file": "f.ts", "line": 3}]}
    return {"objects": [
        {"name": "dbo.spX", "kind": "SQL_PROC", "change": "modified", "risk": {"label": "Medium"}, "unresolved_own": [], "unresolved_in_scope": [],
         "consumers": {"screen": [cons("ScreenA", "UI_COMPONENT", "INFERRED"), cons("ScreenB", "UI_COMPONENT", "CONFIRMED_STATIC")],
                       "api_endpoint": [cons("Ep.Get()", "API_ENDPOINT", "INFERRED")], "business": [cons("Svc.M()", "SERVICE_METHOD", "CONFIRMED_STATIC")]}},
        {"name": "Ctl.Act()", "kind": "API_ENDPOINT", "change": "modified", "risk": None, "unresolved_own": [], "unresolved_in_scope": [], "consumers": {}}],
        "new_unresolved": [], "meta": {"timing_s": {"total_pr_run": 1.5}, "warnings": [], "baseline_commits": {}, "baseline_loaded_at": "t", "baseline_mode": "m"}}


def test_reported_workflows_uses_workflow_kinds_only_and_separates_confirmed():
    allw, conf = R.reported_workflows(fake_result(), ["UI_COMPONENT", "API_ENDPOINT"])
    assert allw == {"ScreenA", "ScreenB", "Ep.Get()", "Ctl.Act()"}       # SERVICE_METHOD and SQL_PROC are not workflows; a changed endpoint is itself affected
    assert conf == {"ScreenB", "Ctl.Act()"}
    assert R.reported_workflows(fake_result(), ["UI_COMPONENT"])[0] == {"ScreenA", "ScreenB"}


def test_unresolved_counts_dedupe_and_classify_not_found():
    u = lambda i, **k: {"edge_id": i, "confidence": "UNRESOLVED", "target_cause": None, "target_kind": "UNRESOLVED", **k}
    res = {"new_unresolved": [u("1", target_cause="referenced_not_found"), u("2", target_cause="no_matching_route")],
           "objects": [{"unresolved_own": [u("2", target_cause="no_matching_route"), u("3", target_cause="dynamic_sql")], "unresolved_in_scope": [u("4", target_kind="SQL_REF"), u("3", target_cause="dynamic_sql")]}]}
    assert R.unresolved_counts(res) == {"unresolved_items": 4, "not_found_items": 3, "introduced_by_the_pr": 2}


# ------------------------------------------------------------------ miss explanations
KINDS = ["UI_COMPONENT", "API_ENDPOINT"]


def mini(unres_on_path=False, chain=2):
    screen = node("web", "UI_COMPONENT", "Screen"); svc = node("web", "UI_SERVICE_METHOD", "Svc.m"); changed = node("db", "SQL_PROC", "dbo.p")
    other = node("web", "UI_COMPONENT", "Lonely")
    ns, es = [screen, svc, changed, other], [edge("CALLS", screen, svc)]
    if unres_on_path:
        ph = node("web", "UNRESOLVED", "no route"); ns.append(ph); es.append(edge("MAKES_REQUEST", svc, ph, "UNRESOLVED", reason="URL part comes from runtime configuration"))
    return graph(ns, es), changed


def result_with(changed, name="dbo.p"):
    return {"objects": [{"id": changed["id"], "name": name, "kind": "SQL_PROC"}] if changed else [], "meta": {}}


def test_explain_miss_unknown_name():
    g, ch = mini(); r = R.explain_miss("Nope", result_with(ch), g, g, KINDS)
    assert r["code"] == "not_in_graph" and "Nope" in r["reason"]


def test_explain_miss_no_changed_object_mapped():
    g, ch = mini(); assert R.explain_miss("Screen", result_with(None), g, g, KINDS)["code"] == "no_changed_object"


def test_explain_miss_unresolved_link_on_the_workflows_dependency_path_names_the_link():
    g, ch = mini(unres_on_path=True); r = R.explain_miss("Screen", result_with(ch), g, g, KINDS)
    assert r["code"] == "unresolved_link_on_path" and "MAKES_REQUEST" in r["reason"] and "runtime configuration" in r["reason"] and "f.x:1" in r["reason"]


def test_explain_miss_no_path_at_all():
    g, ch = mini(); r = R.explain_miss("Lonely", result_with(ch), g, g, KINDS)
    assert r["code"] == "no_path" and "not visible to static analysis" in r["reason"]


def test_explain_miss_depth_limit():
    ns = [node("web", "UI_COMPONENT", "Top")] + [node("web", "METHOD", f"M{i}") for i in range(6)] + [node("db", "SQL_PROC", "dbo.far")]
    g = graph(ns, [edge("CALLS", ns[i], ns[i + 1], line=i + 1) for i in range(len(ns) - 1)])
    r = R.explain_miss("Top", result_with(ns[-1], "dbo.far"), g, g, KINDS, depth=3)
    assert r["code"] == "depth_limit"


def test_explain_miss_reachable_but_not_reported_flags_a_tool_problem():
    g, ch = mini(); svc = next(n for n in g.nodes.values() if n["name"] == "Svc.m")
    g2 = graph(list(g.nodes.values()), list(g.edges.values()) + [edge("CALLS_PROCEDURE", svc, ch)])
    assert R.explain_miss("Screen", result_with(ch), g2, g2, KINDS)["code"] == "reached_but_not_reported"


# ------------------------------------------------------------------ ground-truth file: conversion, validation, commit guard
MD = """# Ground truth input (plain language)

## pr-a-sp-body
The stored procedure body changes.
- FetchEmployeeComponent  — the employee list screen
- `ASPCoreWithAngular.Controllers.EmployeeController.Index()` # endpoint

### pr-d-dynamic-sql
- none

## pr-b-view
Notes: view change
- DepartmentReportComponent
- DepartmentReportComponent
"""


def test_parse_input_md_headings_bullets_comments_none_and_descriptions():
    p = G.parse_input_md(MD)
    s = p["scenarios"]
    assert list(s) == ["pr-a-sp-body", "pr-d-dynamic-sql", "pr-b-view"]
    assert s["pr-a-sp-body"]["affected_workflows"] == ["FetchEmployeeComponent", "ASPCoreWithAngular.Controllers.EmployeeController.Index()"]
    assert s["pr-a-sp-body"]["description"] == "The stored procedure body changes."
    assert s["pr-d-dynamic-sql"]["affected_workflows"] == []
    assert s["pr-b-view"]["affected_workflows"] == ["DepartmentReportComponent"] and s["pr-b-view"]["description"] == "view change"
    assert p["unparsed"] == []


def test_parse_reports_contradictions_instead_of_guessing():
    p = G.parse_input_md("## s\n- none\n- Foo\n")
    assert p["unparsed"] and "both workflows and 'none'" in p["unparsed"][0]


def test_to_yaml_round_trips_and_is_marked_synthetic(tmp_path):
    f = tmp_path / "gt.yml"; f.write_text(G.to_yaml(G.parse_input_md(MD)))
    assert f.read_text().startswith("# EVALUATION GROUND TRUTH") and "SYNTHETIC" in f.read_text()
    d = G.load(f)
    assert d["synthetic"] is True and d["workflow_kinds"] == ["UI_COMPONENT", "API_ENDPOINT"] and d["scenarios"]["pr-d-dynamic-sql"]["affected_workflows"] == []


def test_validate_reports_problems_without_changing_the_file(tmp_path):
    g, _ = mini()
    f = tmp_path / "gt.yml"
    f.write_text(yaml.safe_dump({"version": 1, "workflow_kinds": KINDS, "scenarios": {"pr-a": {"affected_workflows": ["Screen", "Scren", "Screen"]}, "made-up": {"affected_workflows": []}}}))
    before = f.read_text()
    probs = G.validate(G.load(f), g, {"pr-a"})
    assert any("'Scren' is not the name of any" in p and "similar: Screen" in p for p in probs)
    assert any("listed twice" in p for p in probs) and any("'made-up' is not defined" in p for p in probs)
    assert f.read_text() == before


def git_repo(tmp_path):
    r = tmp_path / "r"; r.mkdir()
    sh(["git", "init", "-q", "-b", "main"], cwd=r)
    return r


def test_guard_refuses_untracked_dirty_and_edited_after_commit_ground_truth(tmp_path):
    r = git_repo(tmp_path); gt = r / "eval" / "ground_truth.yml"; gt.parent.mkdir()
    gt.write_text("version: 1\nscenarios: {}\n")
    with pytest.raises(R.GroundTruthNotCommitted, match="not tracked"):
        R.ground_truth_commit(r, gt)
    sh(["git", "add", "-A"], cwd=r)
    with pytest.raises(R.GroundTruthNotCommitted, match="uncommitted"):                 # staged but not committed counts as uncommitted
        R.ground_truth_commit(r, gt)
    sh(["git", *GIT_ID, "commit", "-q", "-m", "gt"], cwd=r)
    info = R.ground_truth_commit(r, gt)
    assert len(info["commit"]) == 40 and info["file"] == "eval/ground_truth.yml" and info["committed_at"].endswith("+00:00")
    gt.write_text("version: 1\nscenarios: {x: {}}\n")                                   # edited AFTER the commit (for example to fit tool output)
    with pytest.raises(R.GroundTruthNotCommitted, match="never edited"):
        R.ground_truth_commit(r, gt)


# ------------------------------------------------------------------ report labelling
def fake_summary(empty_gt=False):
    m = M.workflow_metrics(set() if empty_gt else {"a", "b"}, {"a", "x"}, U)
    sc = {"scenario": "pr-x", "metrics_any_confidence": m, "metrics_confirmed_only": m, "unresolved_and_not_found": {"unresolved_items": 2, "not_found_items": 1, "introduced_by_the_pr": 1},
          "pr_run_duration_s": 2.5, "baseline_freshness": {"status": "fresh"}, "found_only_through_inferred_links": ["a"],
          "misses": [{"workflow": "b", "code": "no_path", "reason": "because"}], "unexpected": [{"workflow": "x", "detail": [{"via": "dbo.p", "confidence": "INFERRED", "evidence": "api:A.cs:7"}]}]}
    o = M.aggregate([m])
    return {"label": R.LABEL, "meta": {"ground_truth": {"file": "eval/ground_truth.yml", "commit": "a" * 40, "committed_at": "t"}, "source_head": "b" * 40, "baseline": "memory",
                                      "baseline_commits": {"web": "c" * 40}, "workflow_kinds": KINDS, "universe_workflows": 6, "run_at": "t", "wall_clock_s": 1},
            "scenarios": [sc], "overall_any_confidence": o, "overall_confirmed_only": o,
            "timing": {"baseline_build_s": 3.0, "pr_run_s": [2.5], "pr_run_mean_s": 2.5, "pr_run_max_s": 2.5}}


def test_report_labels_every_numeric_section_as_synthetic_and_lists_misses():
    md = report.render(fake_summary())
    assert md.lower().count("measured on synthetic data") >= 7
    assert "Not a statement about real code" in md and "outside target" in md
    assert "`pr-x` / `b` - **no_path**: because" in md and "`pr-x` / `x` - via `dbo.p` [INFERRED] at api:A.cs:7" in md
    assert "50% (1/2)" in md and "Found only through INFERRED links" in md
    for section in ("Per scenario", "Overall, any confidence", "Overall, confirmed links only", "Timing", "Misses", "Unexpected workflows"):
        assert section in md
    assert not any(w in md.lower() for w in ("target", "threshold")) or "outside target" in md


def test_report_handles_empty_ground_truth():
    md = report.render(fake_summary(empty_gt=True))
    assert "n/a (empty ground truth)" in md


# ------------------------------------------------------------------ end to end on a TEST-ONLY fixture ground truth
FIXTURE_GT = {"version": 1, "synthetic": True, "workflow_kinds": KINDS, "scenarios": {
    "pr-f-route": {"description": "TEST FIXTURE", "affected_workflows": ["FetchEmployeeComponent", "ASPCoreWithAngular.Controllers.EmployeeController.Index()"],
                    "not_flagged_workflows": ["DepartmentReportComponent"]},
    "pr-e-delete-proc": {"description": "TEST FIXTURE", "affected_workflows": ["DepartmentReportComponent", "ASPCoreWithAngular.Synthetic.Controllers.DepartmentController.Headcount()"],
                         "not_flagged_workflows": ["FetchEmployeeComponent"]},
    "pr-d-dynamic-sql": {"description": "TEST FIXTURE (empty on purpose)", "affected_workflows": []}}}


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    p = Project(tmp_path_factory.mktemp("eval"))
    gt = p.path / "eval" / "ground_truth.yml"; gt.parent.mkdir()
    gt.write_text(yaml.safe_dump(FIXTURE_GT))
    p.commit_all("test-only ground truth")
    out = tmp_path_factory.mktemp("evalout")
    return p, gt, R.run(source=p.path, gt_path=gt, out=out, baseline="memory", tool_root=BACKEND), out


def sc(summary, name):
    return next(s for s in summary["scenarios"] if s["scenario"] == name)


def test_e2e_metrics_misses_and_unexpected_match_hand_derived_expectations(e2e):
    p, gt, s, out = e2e
    f = sc(s, "pr-f-route")
    assert f["metrics_any_confidence"]["recall"] == 1.0 and f["metrics_any_confidence"]["fp"] == 0 and f["metrics_confirmed_only"]["recall"] == 1.0
    e = sc(s, "pr-e-delete-proc")
    # the endpoint is reported (inferred hop); the screen is NOT, because its request URL is built from runtime configuration (UNRESOLVED), so recall is 1/2 with an explained miss
    assert e["metrics_any_confidence"]["recall"] == 0.5 and e["metrics_any_confidence"]["misses"] == ["DepartmentReportComponent"]
    (miss,) = e["misses"]
    assert miss["workflow"] == "DepartmentReportComponent" and miss["code"] == "unresolved_link_on_path" and "runtime configuration" in miss["reason"]
    assert "ASPCoreWithAngular.Synthetic.Controllers.DepartmentController.Headcount()" in e["found_only_through_inferred_links"]
    d = sc(s, "pr-d-dynamic-sql")
    assert d["metrics_any_confidence"]["recall"] is None and d["metrics_any_confidence"]["reported"] == 0 and d["unresolved_and_not_found"]["unresolved_items"] == 1
    assert s["overall_any_confidence"]["scenarios_with_empty_ground_truth"] == 1 and s["overall_any_confidence"]["micro_recall"] == pytest.approx(3 / 4)


def test_e2e_records_ground_truth_commit_freshness_duration_and_labels(e2e):
    p, gt, s, out = e2e
    assert s["meta"]["ground_truth"]["commit"] == subprocess.run(["git", "-C", str(p.path), "log", "-1", "--format=%H", "--", "eval/ground_truth.yml"], capture_output=True, text=True).stdout.strip()
    assert s["label"].startswith("Measured on synthetic data") and all(x["synthetic"] for x in s["scenarios"])
    for x in s["scenarios"]:
        assert x["baseline_freshness"]["status"] == "fresh" and x["pr_run_duration_s"] > 0 and x["baseline_freshness"]["commits"].keys() == {"web", "api", "db"}
    md = (out / "summary.md").read_text()
    assert md.lower().count("measured on synthetic data") >= 7 and "pr-e-delete-proc" in md and (out / "summary.json").exists()
    assert json.loads((out / "summary.json").read_text())["meta"]["workflow_kinds"] == KINDS


def test_e2e_does_not_touch_the_source_repository(e2e):
    p, gt, s, out = e2e
    assert sh(["git", "branch", "--format=%(refname:short)"], cwd=p.path).stdout.split() == ["main"], "scenario branches live only in the temporary clone"
    assert sh(["git", "status", "--porcelain"], cwd=p.path).stdout.strip() == ""
    assert sh(["git", "worktree", "list"], cwd=p.path).stdout.count("\n") == 1


def test_e2e_run_is_refused_when_ground_truth_is_edited_after_commit(e2e, tmp_path):
    p, gt, s, out = e2e
    orig = gt.read_text()
    gt.write_text(orig.replace("TEST FIXTURE (empty on purpose)", "edited to fit"))
    try:
        with pytest.raises(R.GroundTruthNotCommitted):
            R.run(source=p.path, gt_path=gt, out=tmp_path, tool_root=BACKEND)
        assert not (tmp_path / "summary.json").exists(), "a refused run writes no results"
    finally:
        gt.write_text(orig)


def test_e2e_unknown_scenario_in_ground_truth_is_an_error_not_a_skip(tmp_path_factory):
    p = Project(tmp_path_factory.mktemp("evalbad"))
    gt = p.path / "gt.yml"; gt.write_text(yaml.safe_dump({"version": 1, "workflow_kinds": KINDS, "scenarios": {"pr-nope": {"affected_workflows": []}}}))
    p.commit_all("gt")
    with pytest.raises(SystemExit, match="does not define"):
        R.run(source=p.path, gt_path=gt, out=tmp_path_factory.mktemp("o"), tool_root=BACKEND)


def test_eval_label_and_caps_follow_the_synthetic_flag():
    assert R.label_for(True).startswith("Measured on synthetic data") and "flagged synthetic by the configuration" in R.label_for(True)
    plain = R.label_for(False)
    assert "synthetic" not in plain.lower() and plain.startswith("Measured on this repository's author-written scenarios")
    s = {**fake_summary(), "label": plain, "cap": "(measured on this repository's scenarios)"}
    md = report.render(s)
    assert md.count("(measured on this repository's scenarios)") >= 7 and "measured on synthetic data" not in md.lower()


# ------------------------------------------------------------------ current input layout (INVENTED example; never the real input file)
NEW_MD = """# Ground truth input (to be filled in by a person)

Author: A. Tester   Date: 2026-01-01   Source revision of the sample repository reviewed: abc1234

---

## Scenario 1: `pr-a-sp-body` (a stored procedure's body changes)
Reference (orientation only): a made-up note.

- **Change description (your words):** The list procedure skips blank names.
- **Workflows I believe should be flagged:**
  - FetchEmployeeComponent   — the list screen
  - `ASPCoreWithAngular.Controllers.EmployeeController.Index()` # endpoint
- **Workflows that should NOT be flagged:** DepartmentReportComponent; AddEmployeeComponent
- **Notes:** unsure about the second one

## Scenario 2: `pr-b-view` (a view changes)
- **Change description (your words):** A view gains a column.
- **Workflows I believe should be flagged:** none
- **Workflows that should NOT be flagged:** FetchEmployeeComponent, ASPCoreWithAngular.Controllers.EmployeeController.Edit(ASPCoreWithAngular.Models.Employee, int)
- **Notes:**

---

## Optional extra scenarios (up to four more)

### Extra scenario A: name: ______________________
- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

### Extra scenario B: name: pr-extra-b
- **Change description (your words):** An extra one.
- **Workflows I believe should be flagged:** Foo
- **Workflows that should NOT be flagged:** none
- **Notes:** x
"""


def test_current_layout_is_converted_with_both_lists_notes_and_header():
    p = G.parse_input_md(NEW_MD)
    assert p["unparsed"] == [] and list(p["scenarios"]) == ["pr-a-sp-body", "pr-b-view", "pr-extra-b"], p["unparsed"]
    a, b = p["scenarios"]["pr-a-sp-body"], p["scenarios"]["pr-b-view"]
    assert a["description"] == "The list procedure skips blank names." and a["notes"] == "unsure about the second one"
    assert a["affected_workflows"] == ["FetchEmployeeComponent", "ASPCoreWithAngular.Controllers.EmployeeController.Index()"]
    assert a["not_flagged_workflows"] == ["DepartmentReportComponent", "AddEmployeeComponent"]
    assert b["affected_workflows"] == [] and b["notes"] == ""
    assert b["not_flagged_workflows"] == ["FetchEmployeeComponent", "ASPCoreWithAngular.Controllers.EmployeeController.Edit(ASPCoreWithAngular.Models.Employee, int)"], "commas inside a signature do not split"
    assert p["header"] == {"author": "A. Tester", "date": "2026-01-01", "source_revision": "abc1234"}


def test_current_layout_round_trips_through_yaml_and_the_loader(tmp_path):
    f = tmp_path / "gt.yml"; f.write_text(G.to_yaml(G.parse_input_md(NEW_MD)))
    d = G.load(f)
    assert d["author"] == "A. Tester" and d["scenarios"]["pr-a-sp-body"]["not_flagged_workflows"] == ["DepartmentReportComponent", "AddEmployeeComponent"]
    assert d["scenarios"]["pr-b-view"]["affected_workflows"] == [] and d["scenarios"]["pr-extra-b"]["not_flagged_workflows"] == []


def test_an_unfilled_template_is_reported_field_by_field_and_nothing_is_filled_in():
    lines = [l for l in NEW_MD.splitlines() if not l.startswith("  - ")]                      # no nested bullets
    blank = "\n".join((l.split(":**")[0] + ":**") if l.startswith("- **") else l for l in lines)
    blank = blank.replace("A. Tester", "______").replace("2026-01-01", "______").replace("abc1234", "______").replace("name: pr-extra-b", "name: ______")
    p = G.parse_input_md(blank)
    assert p["header"] == {}
    assert all(not s["description"] and not s["affected_workflows"] and not s["not_flagged_workflows"] for s in p["scenarios"].values())
    msgs = p["unparsed"]
    for sc_ in ("pr-a-sp-body", "pr-b-view"):
        for f in ("change description", "workflows i believe should be flagged", "workflows that should not be flagged"):
            assert any(m.startswith(f"{sc_}: missing field '{f}'") for m in msgs), (sc_, f)
    assert not any("Extra scenario" in m for m in msgs), "unused optional extras are ignored"
    assert not any("notes" in m for m in msgs), "notes are optional"
    assert {"header: 'author' is not filled in", "header: 'date' is not filled in", "header: 'source_revision' is not filled in"} <= set(msgs)


def test_missing_fields_blank_lists_and_contradictions_are_reported_not_guessed():
    md = NEW_MD.replace("- **Workflows I believe should be flagged:** none", "- **Workflows I believe should be flagged:**")
    md = md.replace("- **Change description (your words):** An extra one.", "- **Change description (your words):**")
    md = md.replace("DepartmentReportComponent; AddEmployeeComponent", "FetchEmployeeComponent; none")
    msgs = "\n".join(G.parse_input_md(md)["unparsed"])
    assert "pr-b-view: missing field 'workflows i believe should be flagged' (write 'none' if the list is deliberately empty)" in msgs
    assert "pr-extra-b: missing field 'change description'" in msgs
    assert "pr-a-sp-body: both workflows and 'none' were given under 'should NOT be flagged'" in msgs
    assert "listed both as flagged and as NOT flagged: FetchEmployeeComponent" in msgs


def test_extra_scenario_with_fields_but_no_name_is_an_error_and_blank_notes_are_fine():
    md = NEW_MD.replace("name: pr-extra-b", "name: ____")
    msgs = "\n".join(G.parse_input_md(md)["unparsed"])
    assert "Extra scenario B: fields are filled but the scenario name is missing" in msgs
    assert "Notes" not in msgs and "notes" not in msgs


def test_validate_checks_the_not_flagged_names_too(tmp_path):
    g, _ = mini()
    f = tmp_path / "gt.yml"
    f.write_text(yaml.safe_dump({"version": 1, "workflow_kinds": KINDS, "scenarios": {"pr-a": {"affected_workflows": ["Screen"], "not_flagged_workflows": ["Scren", "Screen"]}}}))
    probs = G.validate(G.load(f), g, {"pr-a"})
    assert any("(NOT-flagged list)" in p and "'Scren'" in p and "similar: Screen" in p for p in probs)
    assert any("'Screen' is listed as both flagged and NOT flagged" in p for p in probs)


def test_convert_command_writes_nothing_when_anything_is_missing(tmp_path, capsys):
    src, out = tmp_path / "in.md", tmp_path / "gt.yml"
    src.write_text(NEW_MD.replace("abc1234", "______"))
    with pytest.raises(SystemExit) as e:
        G.main(["convert", str(src), str(out)])
    assert "could not convert" in str(e.value) and not out.exists()
    src.write_text(NEW_MD)
    G.main(["convert", str(src), str(out)])
    assert out.exists() and "3 scenario(s)" in capsys.readouterr().out


# ------------------------------------------------------------------ the separate 'should NOT be flagged' check
def test_not_flagged_check_counts_violations_separately_from_the_main_metrics():
    c = M.not_flagged_check({"x", "y"}, reported_any={"a", "x"}, reported_confirmed={"a"})
    assert (c["listed"], c["violations"], c["violations_confirmed_only"]) == (2, 1, 0)
    assert c["violation_rate"] == 0.5 and c["violation_rate_confirmed_only"] == 0.0 and c["violating_workflows"] == ["x"] and c["not_reported"] == ["y"]
    m = M.workflow_metrics({"a"}, {"a", "x"}, U)
    assert m["fp"] == 1, "the main metrics are unchanged by the list: 'x' is unexpected either way"


def test_not_flagged_check_empty_list_has_undefined_rates_and_aggregate_pools_counts():
    e = M.not_flagged_check(set(), {"a"}, {"a"})
    assert e["listed"] == 0 and e["violation_rate"] is None
    o = M.aggregate_not_flagged([M.not_flagged_check({"x", "y"}, {"x"}, set()), e, M.not_flagged_check({"z"}, set(), set())])
    assert (o["scenarios"], o["scenarios_with_a_list"], o["listed"], o["violations"]) == (3, 2, 3, 1) and o["violation_rate"] == pytest.approx(1 / 3)
    assert M.aggregate_not_flagged([])["violation_rate"] is None


def test_report_has_a_separate_labelled_section_for_the_not_flagged_check():
    s = fake_summary()
    nfc = M.not_flagged_check({"x", "q"}, {"a", "x"}, {"a"})
    s["scenarios"][0]["not_flagged_check"] = {**nfc, "listed_workflows": ["q", "x"], "detail": [{"workflow": "x", "detail": [{"via": "dbo.p", "confidence": "INFERRED", "evidence": "api:A.cs:7"}]}]}
    s["not_flagged_check"] = M.aggregate_not_flagged([nfc])
    md = report.render(s)
    sec = md.split("## Check on the 'should NOT be flagged' lists", 1)[1].split("\n## ", 1)[0]
    assert "measured on synthetic data" in md.split("## Check on the 'should NOT be flagged' lists", 1)[1].split("\n", 1)[0].lower()
    assert "listed: 2 workflow(s) in 1 scenario(s); reported anyway: 1 (50.0%)" in sec and "violation: `pr-x` / `x` - via `dbo.p` [INFERRED] at api:A.cs:7" in sec
    s["not_flagged_check"] = M.aggregate_not_flagged([M.not_flagged_check(set(), set(), set())])
    assert "nothing to check" in report.render(s)


def test_e2e_not_flagged_lists_are_checked_per_scenario_and_overall(e2e):
    p, gt, s, out = e2e
    assert sc(s, "pr-f-route")["not_flagged_check"]["listed_workflows"] == ["DepartmentReportComponent"]
    assert sc(s, "pr-f-route")["not_flagged_check"]["violations"] == 0 and sc(s, "pr-e-delete-proc")["not_flagged_check"]["violations"] == 0
    assert sc(s, "pr-d-dynamic-sql")["not_flagged_check"]["listed"] == 0
    assert s["not_flagged_check"]["listed"] == 2 and s["not_flagged_check"]["violations"] == 0 and s["not_flagged_check"]["scenarios_with_a_list"] == 2
    assert "Check on the 'should NOT be flagged' lists" in (out / "summary.md").read_text()
