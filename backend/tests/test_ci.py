"""CI simulation: file sink shape, comment layout/truncation, advisory exit code, blocking hook, marker + update logic (fakes only), adapters disabled by default.
No test here touches the network: urllib.request.urlopen is replaced by a function that fails the test."""
import argparse, copy, json, pathlib, re
import pytest, yaml
from conftest import ROOT, BACKEND, Project, make_branch
from cdi.eval.scenarios import SCENARIOS
from cdi.ci import adapters, comment, payloads, policy
from cdi.impact import engine
from cdi.linker.graphio import Graph, load_config
from cdi.pipeline import baseline as B, run_pr
from cdi.pipeline.scanrun import ScanRunner

CI = yaml.safe_load((ROOT / "config/ci.yml").read_text())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import urllib.request
    def boom(*a, **k):
        raise AssertionError("network access attempted in a test")
    monkeypatch.setattr(urllib.request, "urlopen", boom)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    p = Project(tmp_path_factory.mktemp("ci"))
    cfg = load_config(p.path / "config")
    runner = ScanRunner(BACKEND, p.path / "config", p.path / "out/work")
    _, _, g, meta = B.full(runner, p.path, cfg)
    fresh = {"commits": meta["commits"], "loaded_at": "2026-01-01T00:00:00+00:00", "mode": "full"}
    for n in ("pr-a-sp-body", "pr-c-ts-service", "pr-e-delete-proc", "pr-f-route"):
        make_branch(p, n, SCENARIOS[n])
    return p, g, fresh


def args_for(world, branch, out, **kw):
    p, g, fresh = world
    d = dict(target="main", pr=branch, name=branch, baseline="files", graph="x", config=str(p.path / "config"), out=str(out), adapter=None,
             enable_azure_adapter=False, pull_request_id=None, blocking=False)
    d.update(kw)
    return argparse.Namespace(**d)


def go(world, branch, out, loader=None, **kw):
    p, g, fresh = world
    ci_override = kw.pop("ci_override", None)
    adapter = kw.pop("adapter_obj", None)
    loader = loader or (lambda cfg, src, gd: (copy.deepcopy(g), fresh))
    return run_pr.run(args_for(world, branch, out, **kw), root=p.path, tool_root=BACKEND, load_baseline=loader, ci_override=ci_override, adapter=adapter)


# ------------------------------------------------------------------ file sink
def test_file_sink_writes_comment_and_status_with_the_documented_shape(world, tmp_path):
    summary, code = go(world, "pr-f-route", tmp_path)
    assert code == 0 and summary["state"] == "succeeded"
    md = (tmp_path / "pr-comment.md").read_text()
    doc = json.loads((tmp_path / "pr-status.json").read_text())
    assert doc["simulated"] is True and doc["shape_verified_against_real_service"] is False
    th = doc["thread"]                                           # Pull Request Threads - Create body
    assert set(th) == {"comments", "status", "properties"} and th["status"] == "active"
    assert th["comments"] == [{"parentCommentId": 0, "content": md, "commentType": "text"}]
    assert th["properties"]["cdiPocMarker"] == {"$type": "System.String", "$value": "cdi-poc:impact-report"}
    st = doc["status"]                                           # Pull Request Statuses - Create body
    assert set(st) == {"state", "description", "context"} and st["state"] in payloads.STATES
    assert st["context"] == {"name": "cdi-poc/impact-analysis", "genre": "cdi-poc"} and len(st["description"]) <= CI["status"]["description_max_chars"]
    assert summary["post"]["adapter"] == "file"


def test_file_sink_overwrites_instead_of_accumulating(world, tmp_path):
    go(world, "pr-f-route", tmp_path); first = (tmp_path / "pr-comment.md").read_text()
    go(world, "pr-a-sp-body", tmp_path); second = (tmp_path / "pr-comment.md").read_text()
    assert first != second and second.count("cdi-poc:impact-report:v1") == 1 and "pr=pr-a-sp-body" in second
    assert sorted(p.name for p in tmp_path.glob("pr-*")) == ["pr-comment.md", "pr-status.json"]


def test_comment_states_its_basis_and_the_advisory_line(world, tmp_path):
    p, g, fresh = world
    go(world, "pr-f-route", tmp_path)
    md = (tmp_path / "pr-comment.md").read_text()
    assert md.splitlines()[0] == "<!-- cdi-poc:impact-report:v1 pr=pr-f-route -->"
    assert "**Advisory:**" in md and "does not block the merge" in md
    for repo, c in fresh["commits"].items():
        assert f"{repo} `{c[:8]}`" in md, f"baseline commit of {repo} missing"
    pr_sha = engine.D.resolve(p.path, "pr-f-route")
    assert f"PR commit `{pr_sha[:8]}`" in md and "target `main`" in md and "merge-base" in md and "baseline loaded 2026-01-01" in md


def test_layout_confirmed_first_inferred_and_convention_last(world, tmp_path):
    go(world, "pr-a-sp-body", tmp_path)
    md = (tmp_path / "pr-comment.md").read_text()
    order = [md.index(h) for h in ("### Changed objects", "### Confirmed consumers", "### Tests to run", "### Unresolved / not found", "### Lower confidence")]
    assert order == sorted(order)
    assert md.index("Naming/file-convention tests") > md.index("### Lower confidence")
    conv_names = ["EmployeeService > should be created", "FetchEmployeeComponent > should create"]
    confirmed_part = md[: md.index("### Lower confidence")]
    assert all(n not in confirmed_part for n in conv_names), "convention tests must not appear before the lower-confidence section"
    assert "over-selects" in md


def test_confirmed_consumer_and_unresolved_items_carry_file_line(world, tmp_path):
    go(world, "pr-f-route", tmp_path)
    md = (tmp_path / "pr-comment.md").read_text()
    assert re.search(r"UI_COMPONENT `FetchEmployeeComponent` — `web:src/app/fetch-employee/fetch-employee.component.ts:19` ⚠ broken by this PR", md)
    assert "`web:src/app/services/employee.service.ts:26`" in md and "no API endpoint" in md
    assert "declared attributes changed" in md and "`route_template` `api/Employee/Index` → `api/Employee/List`" in md


# ------------------------------------------------------------------ truncation
def fake_result(n_consumers=40, n_conv=30, n_unres=12):
    cons = [{"kind": "SERVICE_METHOD", "name": f"Svc{i}.M()", "confidence": "CONFIRMED_STATIC", "broken_by_pr": False,
             "path": [{"repo": "api", "file": f"S{i}.cs", "line": i + 1}]} for i in range(n_consumers)]
    inf = [{**c, "name": f"Inf{i}", "confidence": "INFERRED"} for i, c in enumerate(cons)]
    obj = {"name": "dbo.spX", "kind": "SQL_PROC", "change": "modified", "synthetic": False, "risk": {"label": "Medium", "rule_id": "R5-inferred-path-to-screen"},
           "consumers": {"business": cons + inf}, "unresolved_own": []}
    tests = [{"name": f"conv{i}", "rank": 2, "repo": "web", "file": "a.spec.ts", "line": 1, "mapped_by": ["convention"]} for i in range(n_conv)] + \
            [{"name": f"annot{i}", "rank": 0, "repo": "api", "file": "T.cs", "line": 1, "mapped_by": ["annotation"]} for i in range(15)]
    nu = [{"type": "ROUTES_TO", "source_kind": "HTTP_REQUEST", "source_node": f"GET api/x{i}", "repo": "web", "file": "s.ts", "line": i + 1, "method": "linker:route-match",
           "commit": "a" * 40, "reason": "no endpoint", "consumers_above": []} for i in range(n_unres)]
    return {"meta": {"warnings": [], "timing_s": {"total_pr_run": 1.0}}, "objects": [obj], "tests": tests, "new_unresolved": nu, "files": []}


BASIS = {"pr_name": "pr-9", "pr_branch": "feat", "pr_sha": "1" * 40, "target": "main", "target_sha": "2" * 40, "merge_base": "3" * 40,
         "marker": "cdi-poc:impact-report", "mode": "advisory", "baseline_commits": {"web": "a" * 40, "api": "b" * 40, "db": "c" * 40},
         "baseline_loaded_at": "t", "baseline_mode": "full"}


def test_truncation_lists_n_more_and_counts():
    md, info = comment.build_report_comment(fake_result(), BASIS, CI["comment"])
    assert "… +30 more (full report)" in md                      # 40 confirmed consumers, 10 shown
    assert "Naming/file-convention tests (30)" in md and "… +25 more" in md   # 5 shown
    assert "Inferred consumers (40)" in md and info["chars"] <= info["cap"] and not info["hard_truncated"]


def test_comment_never_exceeds_the_cap_and_keeps_marker_and_basis():
    for cap in (6000, 3000, 1500, 900):
        ccfg = {**CI["comment"], "max_chars": cap}
        md, info = comment.build_report_comment(fake_result(), BASIS, ccfg)
        assert len(md) <= cap, (cap, len(md))
        assert md.splitlines()[0].startswith("<!-- cdi-poc:impact-report:v1") and "**Advisory:**" in md and "**Basis:**" in md
    md, info = comment.build_report_comment(fake_result(), BASIS, {**CI["comment"], "max_chars": 900})
    assert info["hard_truncated"] and "truncated" in md


def test_lower_priority_sections_shrink_before_confirmed_ones():
    big, _ = comment.build_report_comment(fake_result(), BASIS, {**CI["comment"], "max_chars": 20000})
    cap = int(len(big) * 0.6)
    mid, info = comment.build_report_comment(fake_result(), BASIS, {**CI["comment"], "max_chars": cap})
    assert info["scale"] < 1.0 and len(mid) <= cap
    # confirmed consumers are still listed (at least one line) while the convention-test list is cut to counts
    assert "- SERVICE_METHOD `Svc0.M()`" in mid
    assert mid.count("- `conv") <= big.count("- `conv")


# ------------------------------------------------------------------ advisory exit code, skipped, error
def test_advisory_exit_code_is_zero_even_when_policies_would_fire(world, tmp_path):
    summary, code = go(world, "pr-e-delete-proc", tmp_path)               # introduces a referenced-but-undefined proc
    assert code == 0 and summary["state"] == "succeeded" and summary["violations"] == [] and summary["mode"] == "advisory"
    assert "advisory" in json.loads((tmp_path / "pr-status.json").read_text())["status"]["description"]


def test_tool_failure_exits_zero_with_error_state_and_explanatory_comment(world, tmp_path):
    def broken(cfg, src, gd):
        raise RuntimeError("graph store unreachable")
    summary, code = go(world, "pr-f-route", tmp_path, loader=broken)
    assert code == 0 and summary["state"] == "error" and "graph store unreachable" in summary["error"]
    md = (tmp_path / "pr-comment.md").read_text()
    st = json.loads((tmp_path / "pr-status.json").read_text())["status"]
    assert "analysis did not run" in md.lower() and "graph store unreachable" in md and md.startswith("<!-- cdi-poc:impact-report:v1")
    assert st["state"] == "error" and "did not run" in st["description"]


def test_missing_baseline_posts_skipped_comment_not_applicable_and_does_not_build_one(world, tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "analyze", lambda *a, **k: pytest.fail("analysis must not run without a baseline"))
    for loader in (lambda c, s, g: (Graph(), None), lambda c, s, g: (copy.deepcopy(world[1]), None)):
        summary, code = go(world, "pr-f-route", tmp_path, loader=loader)
        assert code == 0 and summary["state"] == "notApplicable" and summary["skipped"] is True
        md = (tmp_path / "pr-comment.md").read_text()
        assert "Baseline missing, analysis skipped" in md and "**Advisory:**" in md and "baseline graph commits: none recorded" in md
        assert json.loads((tmp_path / "pr-status.json").read_text())["status"]["state"] == "notApplicable"
    assert not list(tmp_path.glob("report-*"))


def test_absent_baseline_files_count_as_missing_baseline_not_as_a_tool_error(world, tmp_path):
    p, g, fresh = world
    args = args_for(world, "pr-f-route", tmp_path, baseline="files", graph=str(tmp_path / "no-such-graph-dir"))
    summary, code = run_pr.run(args, root=p.path, tool_root=BACKEND)         # real loader, files that do not exist
    assert code == 0 and summary["state"] == "notApplicable" and summary["skipped"] and summary["error"] is None
    assert "Baseline missing, analysis skipped" in (tmp_path / "pr-comment.md").read_text()


def test_status_states_are_the_documented_enum_and_invalid_ones_are_rejected():
    assert payloads.STATES == ("notSet", "pending", "succeeded", "failed", "error", "notApplicable")
    for s in payloads.STATES:
        assert payloads.status_payload(s, "d", {"name": "n"})["state"] == s
    with pytest.raises(ValueError):
        payloads.status_payload("success", "d", {"name": "n"})
    assert len(payloads.status_payload("succeeded", "x" * 1000, {"name": "n"}, 300)["description"]) == 300


# ------------------------------------------------------------------ blocking hook
def test_blocking_is_off_by_default_in_config():
    assert CI["blocking"]["enabled"] is False
    assert set(CI["blocking"]["policies"]) == set(policy.KNOWN)


def test_blocking_on_fails_only_on_deterministic_policy_with_file_line_evidence(world, tmp_path):
    summary, code = go(world, "pr-e-delete-proc", tmp_path, blocking=True)
    assert code == 1 and summary["state"] == "failed"
    pols = {v["policy"] for v in summary["violations"]}
    assert pols == {"P1-referenced-not-found-introduced"}
    v = [x for x in summary["violations"] if x["repo"] == "api"][0]
    assert (v["file"], v["line"]) == ("Synthetic/DataAccess/DepartmentDataAccess.cs", 24) and v["method"] and len(v["commit"]) == 40 and v["evidence"]
    md = (tmp_path / "pr-comment.md").read_text()
    assert "### Blocking policies (enabled for this run)" in md and "Synthetic/DataAccess/DepartmentDataAccess.cs:24" in md
    assert json.loads((tmp_path / "pr-status.json").read_text())["status"]["state"] == "failed"
    # one deleted procedure = ONE item (not one per reference), with every location listed underneath
    block = md[md.index("### Blocking policies"):md.index("### Changed objects")]
    items = [l for l in block.splitlines() if l.startswith("- ❌")]
    assert len(items) == 1 and "`dbo.spGetDepartmentHeadcount` is referenced but no definition was found (3 locations)" in items[0]
    locs = [l.strip() for l in block.splitlines() if l.startswith("  - `")]
    assert [l.split("`")[1] for l in locs] == ["api:Synthetic/DataAccess/DepartmentDataAccess.cs:24", "api:Synthetic/DataAccess/SqlPatternsDataAccess.cs:42",
                                              "db:synthetic/tests/test_spGetDepartmentHeadcount.sql:7"]
    assert block.count("reason:") == 1 and "no definition was found in any scanned repo" in block
    assert len(summary["violations"]) == 3, "the flat violations (3 raw hits) are still available in the summary"

    summary, code = go(world, "pr-f-route", tmp_path, blocking=True)
    block = (tmp_path / "pr-comment.md").read_text()
    assert block.count("- ❌") == 1 and "`GET api/Employee/Index`" in block and "web:src/app/services/employee.service.ts:26" in block
    assert code == 1 and {v["policy"] for v in summary["violations"]} == {"P2-route-unmatched-introduced"}
    assert (summary["violations"][0]["file"], summary["violations"][0]["line"]) == ("src/app/services/employee.service.ts", 26)


def test_blocking_never_fails_on_a_risk_label_alone(world, tmp_path):
    summary, code = go(world, "pr-c-ts-service", tmp_path, blocking=True)       # High label (R4) but nothing unresolved introduced
    res_label = json.loads((tmp_path / "pr-status.json").read_text())["status"]["description"]
    assert code == 0 and summary["state"] == "succeeded" and "highest risk label High" in res_label


def test_blocking_via_config_flag_and_policy_list(world, tmp_path):
    summary, code = go(world, "pr-f-route", tmp_path, ci_override={"blocking": {"enabled": True}})
    assert code == 1
    summary, code = go(world, "pr-f-route", tmp_path, ci_override={"blocking": {"enabled": True, "policies": ["P1-referenced-not-found-introduced"]}})
    assert code == 0, "a policy that is not listed in config can never fail a run"
    summary, code = go(world, "pr-f-route", tmp_path, ci_override={"blocking": {"enabled": True, "policies": []}})
    assert code == 0


def test_blocking_does_not_turn_tool_errors_into_failures(world, tmp_path):
    def broken(cfg, src, gd):
        raise RuntimeError("boom")
    summary, code = go(world, "pr-f-route", tmp_path, loader=broken, blocking=True)
    assert code == 0 and summary["state"] == "error"


def _hit(**kw):
    base = {"repo": "api", "file": "A.cs", "line": 7, "method": "m", "commit": "a" * 40, "evidence": "x", "reason": "r", "synthetic": False,
            "source_node": "n", "source_kind": "SQL_REF", "type": "RESOLVES_TO", "confidence": "UNRESOLVED", "target_cause": "referenced_not_found",
            "target_kind": "UNRESOLVED", "target": "t", "attrs": {}}
    base.update(kw)
    return base


def test_grouping_collapses_hits_on_the_same_missing_object_and_lists_locations():
    res = {"new_unresolved": [
        _hit(source_node="dbo.spGone", file="A.cs", line=7, method="linker:sql-name-match", attrs={"referenced_from": ["api:A.cs:7", "api:B.cs:42"]}),
        _hit(source_node="DBO.SPGONE", repo="db", file="t.sql", line=3, method="linker:sql-name-match"),          # same object, different case/repo
        _hit(type="CALLS_PROCEDURE", target_kind="SQL_REF", target_cause=None, source_node="TestX", source_kind="TEST", target="dbo.spGone",
             repo="db", file="t.sql", line=3, method="scriptdom:exec-procedure"),                                     # scanner-level reference, same file:line
        _hit(source_node="dbo.spOther", file="C.cs", line=9)]}
    flat = policy.evaluate(res, ["P1-referenced-not-found-introduced"])
    assert len(flat) == 4
    groups = policy.group(flat)
    assert [g["missing_object"].lower() for g in groups] == ["dbo.spgone", "dbo.spother"]
    gone = groups[0]
    assert [(l["repo"], l["file"], l["line"]) for l in gone["locations"]] == [("api", "A.cs", 7), ("api", "B.cs", 42), ("db", "t.sql", 3)]
    db_loc = gone["locations"][2]
    assert db_loc["methods"] == ["linker:sql-name-match", "scriptdom:exec-procedure"], "two hits at the same file:line are merged into one location"
    assert gone["locations"][1]["methods"] == [], "a site known only from referenced_from has no method of its own"
    assert len(groups[1]["locations"]) == 1


def test_grouping_keeps_different_policies_and_objects_apart():
    res = {"new_unresolved": [_hit(source_node="dbo.p"), _hit(type="ROUTES_TO", target_cause="no_matching_route", source_node="dbo.p")]}
    groups = policy.group(policy.evaluate(res, list(policy.KNOWN)))
    assert {(g["policy"], g["missing_object"]) for g in groups} == {("P1-referenced-not-found-introduced", "dbo.p"), ("P2-route-unmatched-introduced", "dbo.p")}


def test_comment_groups_blocking_hits_per_missing_object():
    res = fake_result(n_consumers=1, n_conv=0, n_unres=0)
    hits = [policy._violation("P1-referenced-not-found-introduced", {"repo": r, "file": f, "line": l, "method": m, "commit": "a" * 40, "type": "RESOLVES_TO",
                                                                      "reason": "no definition", "evidence": "e", "attrs": {}}, "`dbo.spX` is referenced but no definition was found", "dbo.spX")
            for r, f, l, m in (("api", "A.cs", 24, "m1"), ("api", "B.cs", 42, "m1"), ("db", "t.sql", 7, "m2"))]
    md, _ = comment.build_report_comment(res, BASIS, CI["comment"], hits, blocking=True)
    block = md[md.index("### Blocking policies"):md.index("### Changed objects")]
    assert block.count("- ❌") == 1 and "(3 locations)" in block and block.count("\n  - `") == 3 and block.count("reason:") == 1
    md1, _ = comment.build_report_comment(res, BASIS, CI["comment"], hits[:1], blocking=True)
    assert "(1 location)" in md1


def test_policy_unit_behaviour_and_unknown_ids():
    base = {"repo": "api", "file": "A.cs", "line": 7, "method": "m", "commit": "a" * 40, "evidence": "x", "reason": "r", "synthetic": False, "source_node": "n"}
    res = {"new_unresolved": [
        {**base, "type": "RESOLVES_TO", "confidence": "UNRESOLVED", "target_cause": "referenced_not_found", "target_kind": "UNRESOLVED"},
        {**base, "type": "ROUTES_TO", "confidence": "UNRESOLVED", "target_cause": "no_matching_route", "target_kind": "UNRESOLVED"},
        {**base, "type": "EXECUTES_DYNAMIC_SQL", "confidence": "UNRESOLVED", "target_cause": "dynamic_sql", "target_kind": "UNRESOLVED"},
        {**base, "type": "MAKES_REQUEST", "confidence": "UNRESOLVED", "target_cause": "config_built_route", "target_kind": "UNRESOLVED"}]}
    got = policy.evaluate(res, list(policy.KNOWN))
    assert sorted(v["policy"] for v in got) == ["P1-referenced-not-found-introduced", "P2-route-unmatched-introduced"]
    assert all(v["file"] == "A.cs" and v["line"] == 7 for v in got)
    assert policy.evaluate(res, []) == []
    with pytest.raises(ValueError, match="unknown blocking policy"):
        policy.evaluate(res, ["P9-made-up"])


# ------------------------------------------------------------------ adapters: disabled by default, marker, update logic (fake server)
class FakeServer:
    """In-memory stand-in for the Azure DevOps endpoints used by the adapter (no network)."""
    def __init__(self, threads=None):
        self.threads, self.calls, self.statuses, self._id = list(threads or []), [], [], 100

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if method == "GET" and url.split("?")[0].endswith("/threads"):
            return 200, {"value": copy.deepcopy(self.threads), "count": len(self.threads)}
        if method == "POST" and url.split("?")[0].endswith("/threads"):
            self._id += 1
            t = {"id": self._id, "comments": [{"id": 1, "parentCommentId": 0, "content": body["comments"][0]["content"], "commentType": "text"}],
                 "status": body["status"], "properties": body["properties"], "isDeleted": False}
            self.threads.append(t)
            return 200, t
        m = re.search(r"/threads/(\d+)/comments/(\d+)\?", url)
        if method == "PATCH" and m:
            t = next(t for t in self.threads if t["id"] == int(m.group(1)))
            c = next(c for c in t["comments"] if c["id"] == int(m.group(2)))
            c["content"] = body["content"]
            return 200, c
        if method == "POST" and url.split("?")[0].endswith("/statuses"):
            self.statuses.append(body)
            return 200, {"id": len(self.statuses), **body}
        raise AssertionError(f"unexpected call {method} {url}")


AZ = {"organization": "org-x", "project": "proj-x", "repository_id": "repo-x", "api_version": "7.1", "token_env": "FAKE_TOKEN_ENV", "auth_scheme": "basic"}
MARK = CI["comment"]["marker"]
ENV = {"FAKE_TOKEN_ENV": "not-a-real-token-123"}


def adapter(server, enabled=True, env=ENV, cfg=AZ, pr=7):
    return adapters.AzureDevOpsAdapter(cfg, pr, enabled=enabled, transport=server, environ=env)


STATUS = payloads.status_payload("succeeded", "advisory", {"name": "n", "genre": "g"})


def test_marker_is_in_the_comment_body_and_is_stable():
    a, b = payloads.marker_text(MARK, "pr-1"), payloads.marker_text(MARK, "pr-1")
    assert a == b and MARK in a and a.startswith("<!--") and a.endswith("-->")


def test_first_run_creates_a_thread_with_marker_in_body_and_property():
    srv = FakeServer()
    res = adapter(srv).post("pr-7", f"{payloads.marker_text(MARK, 'pr-7')}\nhello", STATUS, MARK)
    assert res["action"] == "created"
    methods = [(m, u.split("/pullRequests/")[1]) for m, u, *_ in srv.calls]
    assert methods == [("GET", "7/threads?api-version=7.1"), ("POST", "7/threads?api-version=7.1"), ("POST", "7/statuses?api-version=7.1")]
    body = srv.calls[1][3]
    assert MARK in body["comments"][0]["content"] and body["properties"]["cdiPocMarker"]["$value"] == MARK and body["comments"][0]["parentCommentId"] == 0


def test_second_run_updates_its_own_thread_instead_of_creating_another():
    srv = FakeServer()
    a = adapter(srv)
    a.post("pr-7", f"{payloads.marker_text(MARK, 'pr-7')}\nv1", STATUS, MARK)
    srv.calls.clear()
    res = a.post("pr-7", f"{payloads.marker_text(MARK, 'pr-7')}\nv2", STATUS, MARK)
    assert res["action"] == "updated" and len(srv.threads) == 1
    assert srv.threads[0]["comments"][0]["content"].endswith("v2")
    kinds = [(m, re.sub(r"^.*/pullRequests/", "", u)) for m, u, *_ in srv.calls]
    assert ("PATCH", f"7/threads/{srv.threads[0]['id']}/comments/1?api-version=7.1") in kinds
    assert not [1 for m, u, *_ in srv.calls if m == "POST" and u.split("?")[0].endswith("/threads")], "must not create a new thread"
    assert srv.calls[1][3] == payloads.comment_update_payload(f"{payloads.marker_text(MARK, 'pr-7')}\nv2")


def test_finds_own_thread_among_other_threads_ignores_deleted_and_foreign_ones():
    foreign = {"id": 1, "isDeleted": False, "comments": [{"id": 1, "content": "a human comment"}]}
    deleted = {"id": 2, "isDeleted": True, "comments": [{"id": 1, "content": f"old {MARK}"}]}
    deleted_comment = {"id": 3, "isDeleted": False, "comments": [{"id": 1, "isDeleted": True, "content": f"gone {MARK}"}]}
    mine = {"id": 4, "isDeleted": False, "comments": [{"id": 1, "content": "bot"}, {"id": 2, "content": f"<!-- {MARK}:v1 pr=x --> body"}]}
    assert adapter(FakeServer([foreign, deleted, deleted_comment, mine])).find_own_thread(MARK) == (4, 2)
    assert adapter(FakeServer([foreign, deleted, deleted_comment])).find_own_thread(MARK) is None
    by_prop = {"id": 9, "isDeleted": False, "comments": [{"id": 5, "content": "edited by someone"}], "properties": {"cdiPocMarker": {"$type": "System.String", "$value": MARK}}}
    assert adapter(FakeServer([by_prop])).find_own_thread(MARK) == (9, 5)


def test_status_is_posted_with_the_same_context_every_run():
    srv = FakeServer(); a = adapter(srv)
    a.post("pr-7", f"{payloads.marker_text(MARK, 'pr-7')}\nx", STATUS, MARK); a.post("pr-7", f"{payloads.marker_text(MARK, 'pr-7')}\ny", STATUS, MARK)
    assert len(srv.statuses) == 2 and srv.statuses[0]["context"] == srv.statuses[1]["context"] == {"name": "n", "genre": "g"}


def test_token_is_only_used_as_a_header_and_never_in_urls_or_bodies():
    srv = FakeServer(); adapter(srv).post("pr-7", "<!-- m --> x", STATUS, MARK)
    for m, u, h, b in srv.calls:
        assert ENV["FAKE_TOKEN_ENV"] not in u and ENV["FAKE_TOKEN_ENV"] not in json.dumps(b or {})
        assert h["Authorization"].startswith("Basic ")


def test_azure_adapter_is_disabled_by_default_and_makes_no_call(world, tmp_path):
    srv = FakeServer()
    a = adapters.build_adapter("azure", CI, tmp_path, transport=srv, environ=ENV, pull_request_id=7)       # enable flag NOT given
    assert isinstance(a, adapters.AzureDevOpsAdapter) and a.enabled is False
    with pytest.raises(adapters.AdapterDisabled, match="disabled"):
        a.post("pr-7", "x", STATUS, MARK)
    with pytest.raises(adapters.AdapterDisabled):
        a.find_own_thread(MARK)
    assert srv.calls == []
    assert isinstance(adapters.build_adapter(None, CI, tmp_path), adapters.FileSink) and isinstance(adapters.build_adapter("file", CI, tmp_path), adapters.FileSink)
    assert CI["adapter"]["default"] == "file"
    # through the runner: requesting azure without the enable flag is reported, never executed, and does not fail an advisory run
    summary, code = go(world, "pr-f-route", tmp_path, adapter_obj=a)
    assert code == 0 and "AdapterDisabled" in summary["post"]["error"] and srv.calls == []
    # the result is not lost: the file sink is the fallback
    assert (tmp_path / "pr-comment.md").exists() and json.loads((tmp_path / "pr-status.json").read_text())["simulated"] is True
    assert summary["post"]["fallback"]["adapter"] == "file"


def test_enabled_adapter_still_refuses_placeholders_and_missing_token():
    srv = FakeServer()
    with pytest.raises(adapters.AdapterDisabled, match="placeholder"):
        adapters.AzureDevOpsAdapter(CI["adapter"]["azure"], 7, enabled=True, transport=srv, environ=ENV).post("p", "x", STATUS, MARK)
    with pytest.raises(adapters.AdapterDisabled, match="not set"):
        adapter(srv, env={}).post("p", "x", STATUS, MARK)
    with pytest.raises(adapters.AdapterDisabled, match="pull request id"):
        adapter(srv, pr=None).post("p", "x", STATUS, MARK)
    assert srv.calls == []


def test_real_transport_is_only_built_once_enabled(monkeypatch):
    a = adapters.AzureDevOpsAdapter(AZ, 7, enabled=False, environ=ENV)
    with pytest.raises(adapters.AdapterDisabled):
        a.find_own_thread(MARK)
    assert a._transport is None                      # no transport was constructed while disabled


# ------------------------------------------------------------------ pipeline file and repo hygiene
def test_azure_pipelines_yaml_uses_placeholders_only_and_stays_advisory():
    text = (ROOT / "azure-pipelines.yml").read_text()
    doc = yaml.safe_load(text)
    scripts = " ".join(str(s.get("script", "")) for s in doc["steps"])
    assert "pipeline/run_pr.sh" in scripts
    assert "--enable-azure-adapter" not in scripts and "--adapter azure" not in scripts and "--blocking" not in scripts
    assert all(s.get("continueOnError") for s in doc["steps"] if "run_pr" in str(s.get("script", "")))
    live = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert "dev.azure.com" not in text and "AZDO_TOKEN" not in live and not re.search(r"(?i)(pat|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9]{20,}", text)
    assert "<TARGET_BRANCH>" in text or "<AGENT_POOL>" in text


def test_ci_config_has_only_placeholders_and_no_secrets():
    az = CI["adapter"]["azure"]
    assert all(az[k].startswith("<") and az[k].endswith(">") for k in ("organization", "project", "repository_id"))
    assert az["token_env"] == "AZDO_TOKEN" and "token" not in {k for k in az if k != "token_env" and k != "auth_scheme"}
    assert "placeholder, unvalidated" in (ROOT / "config/ci.yml").read_text()
