"""The GitHub PR and baseline flows against the in-memory fake GitHub server and real git repos built from the fixture.
Covered: target from the event, baseline never written by a PR run, baseline current / behind / ahead / unmatched, cache missing, schema mismatch,
fork skip, advisory failures, no token, the baseline flow's trust and size rules."""
import json, os, pathlib, subprocess
import pytest
from conftest import BACKEND, FIXTURE_CONFIG, GIT_ID, Project, make_branch, sh
from fake_github import FakeGitHub, TOKEN
from cdi import store as S
from cdi.eval.scenarios import load_scenarios
from cdi.github import flow
from cdi.github.summary import Summary
from cdi.linker.graphio import load_config
from cdi.pipeline import baseline as B
from cdi.pipeline.scanrun import ScanRunner
from cdi.store.json_store import JsonStore
from conftest import FIXTURE_SCENARIOS

SCEN = load_scenarios(FIXTURE_SCENARIOS)


def sha(p, rev):
    return sh(["git", "rev-parse", rev], cwd=p.path).stdout.strip()


def build_baseline(p, path, rev="HEAD"):
    cfg = load_config(p.path / ".cdi/config.yml")
    runner = ScanRunner(BACKEND, cfg["dir"], p.path / "out/work")
    _, _, g, meta = B.full(runner, p.path, cfg, rev)
    JsonStore(path).write_full(g, S.make_freshness(g, meta["commits"], "full", to_commit=meta["rev"]))
    return g, meta


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """main with a baseline built from it; branch pr-f-route (one controller edit) branched from main."""
    p = Project(tmp_path_factory.mktemp("ghworld"))
    bl = tmp_path_factory.mktemp("ghbase") / "baseline.json"
    build_baseline(p, bl)
    make_branch(p, "pr-f-route", SCEN["pr-f-route"])
    return p, bl


def event_file(tmp_path, p, head="pr-f-route", base="main", number=7, head_repo="o/r", name="pull_request"):
    ev = {"action": "synchronize", "pull_request": {"number": number, "base": {"ref": base, "sha": sha(p, base) if base == "main" else "0" * 40, "repo": {"full_name": "o/r"}},
                                                    "head": {"ref": head, "sha": sha(p, head), "repo": {"full_name": head_repo}}}}
    f = tmp_path / "event.json"
    f.write_text(json.dumps(ev))
    return f


def env_for(tmp_path, gh, ev, token=TOKEN, **extra):
    e = {"GITHUB_EVENT_PATH": str(ev), "GITHUB_EVENT_NAME": "pull_request", "GITHUB_API_URL": gh.url, "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
         "GITHUB_RUN_ID": "99", "GITHUB_SERVER_URL": "https://github.example", "GITHUB_REPOSITORY": "o/r"}
    if token:
        e["GITHUB_TOKEN"] = token
    e.update(extra)
    return e


def run_flow(tmp_path, p, bl, gh, ev=None, env_extra=None, **kw):
    ev = ev or event_file(tmp_path, p)
    env = env_for(tmp_path, gh, ev, **(env_extra or {}))
    code = flow.run_pr_flow(root=p.path, config=p.path / ".cdi/config.yml", store_path=bl, out=tmp_path / "out", environ=env, tool_root=BACKEND, **kw)
    summary = (tmp_path / "summary.md").read_text() if (tmp_path / "summary.md").exists() else ""
    return code, summary


def comment_body(gh, number=7):
    (c,) = gh.comments[number]
    return c["body"]


# ---------------------------------------------------------------- happy path, target, baseline never written
def test_pr_run_comments_sets_status_and_leaves_the_baseline_untouched(world, tmp_path):
    p, bl = world
    before = (bl.read_bytes(), bl.stat().st_mtime_ns)
    with FakeGitHub() as gh:
        code, summary = run_flow(tmp_path, p, bl, gh)
        body = comment_body(gh)
        assert code == 0 and "<!-- cdi-poc:impact-report:v1" in body and "**Advisory:**" in body
        assert "Baseline note" not in body, "a current baseline needs no warning"
        (st,) = gh.statuses
        assert st["state"] == "success" and st["context"] == "cdi-poc/impact-analysis" and st["sha"] == sha(p, "pr-f-route")
        assert st["target_url"] == "https://github.example/o/r/actions/runs/99"
        assert "Comment created" in summary and "Commit status" in summary
        code, summary = run_flow(tmp_path, p, bl, gh)                       # second run: same single comment, updated or unchanged
        assert len(gh.comments[7]) == 1 and "Comment " in summary
    assert (bl.read_bytes(), bl.stat().st_mtime_ns) == before, "a PR run never writes the baseline"


def test_pr_flow_cannot_write_any_store(world, tmp_path, monkeypatch):
    p, bl = world
    def boom(*a, **k):
        raise AssertionError("a PR run tried to write the baseline store")
    monkeypatch.setattr(JsonStore, "write_full", boom); monkeypatch.setattr(JsonStore, "sync", boom)
    with FakeGitHub() as gh:
        code, _ = run_flow(tmp_path, p, tmp_path / "absent.json", gh)          # forces the full-build fallback path as well
    assert code == 0 and not (tmp_path / "absent.json").exists()


def test_target_comes_from_the_event_base_ref_not_from_config(world, tmp_path, monkeypatch):
    p, bl = world
    monkeypatch.setenv("CDI__branches__base", "not-the-base-branch")        # config default would break the run if it were used
    with FakeGitHub() as gh:
        code, summary = run_flow(tmp_path, p, bl, gh)
        assert code == 0 and "target `main` @" in comment_body(gh) and "target `main` (from the PR event)" in summary
        assert gh.statuses[0]["state"] == "success"


def test_unknown_base_ref_is_an_advisory_problem_not_a_crash(world, tmp_path):
    p, bl = world
    with FakeGitHub() as gh:
        ev = event_file(tmp_path, p, base="release-9")
        code, summary = run_flow(tmp_path, p, bl, gh, ev=ev)
        assert code == 0 and "release-9" in summary and gh.requests == []


def test_event_without_a_pull_request_is_a_clear_message(world, tmp_path):
    p, bl = world
    f = tmp_path / "e.json"; f.write_text(json.dumps({"ref": "refs/heads/main"}))
    with FakeGitHub() as gh:
        code, summary = run_flow(tmp_path, p, bl, gh, ev=f)
    assert code == 0 and "not a pull_request run" in summary and gh.requests == []


# ---------------------------------------------------------------- baseline freshness vs the PR's merge-base
def test_baseline_cache_missing_falls_back_to_a_full_build_and_says_so(world, tmp_path):
    p, bl = world
    with FakeGitHub() as gh:
        code, summary = run_flow(tmp_path, p, tmp_path / "no-cache.json", gh)
        body = comment_body(gh)
        assert code == 0 and "**Baseline note:**" in body and "FULL build" in body and "no baseline was found in the cache" in body
        assert "stored baseline was not modified" in body and "full-fallback" in body
        assert gh.statuses[0]["state"] == "success"
    assert "FULL build" in summary and not (tmp_path / "no-cache.json").exists()


def test_baseline_from_another_schema_version_is_rejected_and_rebuilt_in_memory(world, tmp_path):
    p, bl = world
    bad = tmp_path / "old.json"
    doc = json.loads(bl.read_text()); doc["schema_version"] = S.SCHEMA_VERSION + 5
    bad.write_text(json.dumps(doc))
    before = bad.read_bytes()
    with FakeGitHub() as gh:
        code, _ = run_flow(tmp_path, p, bad, gh)
        body = comment_body(gh)
    assert code == 0 and "rejected" in body and "schema version" in body and "FULL build" in body
    assert bad.read_bytes() == before


def test_baseline_not_matching_the_merge_base_falls_back_to_a_full_build(world, tmp_path):
    p, bl = world
    bogus = tmp_path / "bogus.json"
    doc = json.loads(bl.read_text()); doc["freshness"]["commits"] = {r: "f" * 40 for r in doc["freshness"]["commits"]}
    bogus.write_text(json.dumps(doc))
    with FakeGitHub() as gh:
        code, _ = run_flow(tmp_path, p, bogus, gh)
        body = comment_body(gh)
    assert code == 0 and "cannot be matched to the PR's merge-base" in body and "FULL build" in body


def test_baseline_from_unrelated_history_is_unmatched_too(world, tmp_path):
    p, bl = world
    tree = sh(["git", "rev-parse", "HEAD^{tree}"], cwd=p.path).stdout.strip()
    orphan = sh(["git", *GIT_ID, "commit-tree", tree, "-m", "unrelated"], cwd=p.path).stdout.strip()
    f = tmp_path / "other.json"
    doc = json.loads(bl.read_text()); doc["freshness"]["commits"] = {r: orphan for r in doc["freshness"]["commits"]}
    f.write_text(json.dumps(doc))
    with FakeGitHub() as gh:
        run_flow(tmp_path, p, f, gh)
        assert "FULL build" in comment_body(gh)


@pytest.fixture(scope="module")
def moved(tmp_path_factory):
    """main advanced in the db folder AFTER the baseline was built (baseline = c0, main = c1). PR branches: pr-late from c1, pr-early from c0."""
    p = Project(tmp_path_factory.mktemp("ghmoved"))
    bl = tmp_path_factory.mktemp("ghmovedbase") / "baseline.json"
    build_baseline(p, bl)
    f = p.path / "samples/db/synthetic/procedures/spGetCityList.sql"
    f.write_text(f.read_text() + "\n-- later change on main\n")
    p.commit_all("main moves on")
    make_branch(p, "pr-late", SCEN["pr-f-route"])
    make_branch(p, "pr-early", SCEN["pr-f-route"], base="HEAD~1")
    return p, bl


def test_baseline_that_is_an_ancestor_says_how_many_commits_behind_and_does_not_rebuild(moved, tmp_path):
    p, bl = moved
    with FakeGitHub() as gh:
        code, summary = run_flow(tmp_path, p, bl, gh, ev=event_file(tmp_path, p, head="pr-late"))
        body = comment_body(gh)
    assert code == 0 and "baseline for 'db' is 1 commit(s) behind the PR's merge-base" in body
    assert "'web'" not in body.split("Baseline note")[1].split("\n")[0], "only the repo that moved is reported"
    assert "FULL build" not in body and "behind" in summary


def test_baseline_ahead_of_the_merge_base_is_flagged_but_usable(moved, tmp_path):
    p, bl = moved
    # a baseline built from c1 (newer than pr-early's merge-base c0)
    ahead = tmp_path / "ahead.json"
    build_baseline(p, ahead)
    with FakeGitHub() as gh:
        code, _ = run_flow(tmp_path, p, ahead, gh, ev=event_file(tmp_path, p, head="pr-early"))
        body = comment_body(gh)
    assert code == 0 and "AHEAD of the PR's merge-base" in body and "FULL build" not in body


# ---------------------------------------------------------------- forks, failures, token
def test_fork_pull_requests_are_skipped_with_a_summary_message(world, tmp_path):
    p, bl = world
    with FakeGitHub() as gh:
        ev = event_file(tmp_path, p, head_repo="stranger/r")
        code, summary = run_flow(tmp_path, p, bl, gh, ev=ev)
        assert gh.requests == [], "nothing is sent to GitHub for a fork PR"
    assert code == 0 and "Skipped" in summary and "fork" in summary and "stranger/r" in summary and not (tmp_path / "out").exists()


@pytest.mark.parametrize("code_,needle", [(403, "pull-requests: write"), (404, "not visible"), (422, "Validation failed")])
def test_comment_failures_are_advisory_and_visible_in_the_summary(world, tmp_path, capsys, code_, needle):
    p, bl = world
    with FakeGitHub() as gh:
        gh.deny["comments"] = code_
        code, summary = run_flow(tmp_path, p, bl, gh)
        assert len(gh.statuses) == 1
    assert code == 0 and "could not post to GitHub" in summary and needle in summary and str(code_) in summary
    assert "::warning title=cdi::" in capsys.readouterr().out
    assert (tmp_path / "out" / "report-pr-7.md").exists(), "the report files are still written"


def test_status_403_is_advisory(world, tmp_path):
    p, bl = world
    with FakeGitHub() as gh:
        gh.deny["statuses"] = 403
        code, summary = run_flow(tmp_path, p, bl, gh)
        assert len(gh.comments[7]) == 1
    assert code == 0 and "statuses: write" in summary


def test_without_a_token_nothing_is_posted(world, tmp_path):
    p, bl = world
    with FakeGitHub() as gh:
        code, summary = run_flow(tmp_path, p, bl, gh, env_extra={"GITHUB_TOKEN": ""})
        assert code == 0 and gh.requests == []
    assert "GITHUB_TOKEN is not set" in summary and (tmp_path / "out" / "pr-comment.md").exists()


def test_pr_too_large_is_skipped_with_a_clear_comment(world, tmp_path, monkeypatch):
    p, bl = world
    make_branch(p, "pr-two", {**SCEN["pr-a-sp-body"], **SCEN["pr-b-view"]})
    monkeypatch.setenv("CDI__limits__max_changed_files", "1")
    with FakeGitHub() as gh:
        code, _ = run_flow(tmp_path, p, bl, gh, ev=event_file(tmp_path, p, head="pr-two"))
        assert code == 0 and "PR too large" in comment_body(gh) and gh.statuses[0]["state"] == "success"


# ---------------------------------------------------------------- baseline flow
def push_env(tmp_path, ref="refs/heads/main", name="push"):
    return {"GITHUB_EVENT_NAME": name, "GITHUB_REF": ref, "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md")}


def run_baseline(tmp_path, p, target, env, capsys=None):
    code = flow.run_baseline_flow(root=p.path, config=p.path / ".cdi/config.yml", store_path=target, out=tmp_path / "out", environ=env, tool_root=BACKEND)
    return code, (tmp_path / "summary.md").read_text() if (tmp_path / "summary.md").exists() else ""


def test_baseline_is_built_only_for_a_push_to_the_base_branch(world, tmp_path):
    p, _ = world
    target = tmp_path / "b.json"
    code, summary = run_baseline(tmp_path, p, target, push_env(tmp_path))
    assert code == 0 and target.exists()
    doc = json.loads(target.read_text())
    assert doc["schema_version"] == S.SCHEMA_VERSION and set(doc["freshness"]["commits"]) == {"web", "api", "db"}
    assert "Baseline size" in summary and f"{target.stat().st_size:,}" in summary and "schema version 1" in summary


@pytest.mark.parametrize("ref,name", [("refs/pull/7/merge", "pull_request"), ("refs/heads/feature", "push"), ("refs/heads/main", "workflow_dispatch")])
def test_baseline_refuses_any_other_event_or_branch(world, tmp_path, ref, name):
    p, _ = world
    target = tmp_path / "b.json"
    code, summary = run_baseline(tmp_path, p, target, push_env(tmp_path, ref, name))
    assert code == 2 and not target.exists() and "Baseline not built" in summary and "only by a push to the base branch" in summary


def test_oversized_baseline_warns_in_the_summary_and_annotation_but_is_saved(world, tmp_path, capsys):
    p, _ = world
    target = tmp_path / "b.json"
    code, summary = run_baseline(tmp_path, p, target, {**push_env(tmp_path), "CDI__limits__baseline_max_bytes": "1000"})
    assert code == 0 and target.exists() and "over the configured limit of 1,000" in summary
    out = capsys.readouterr().out
    assert "::warning title=cdi baseline size::" in out and '"over_limit": true' in out


def test_baseline_limit_defaults_to_a_marked_placeholder():
    cfg = load_config(FIXTURE_CONFIG, environ={})
    assert cfg["limits"]["baseline_max_bytes"] == 52428800
    assert "baseline_max_bytes" in (BACKEND / "src/cdi/config/profiles/_base.yml").read_text() and "placeholder, unvalidated" in (BACKEND / "src/cdi/config/profiles/_base.yml").read_text()
