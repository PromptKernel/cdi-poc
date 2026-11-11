"""Static checks of the example workflows and the composite action: the security rules are properties of these files, so they are tested."""
import re, pathlib
import pytest, yaml
from conftest import ROOT

WF = ROOT / "config.example/github/workflows"
ACTION = ROOT / ".github/actions/cdi/action.yml"
FILES = {"baseline": WF / "cdi-baseline.yml", "pr": WF / "cdi-pr.yml"}
SHA = re.compile(r"^[0-9a-f]{40}$")
# the verified pins (docs/github-flow.md lists how each was looked up)
PINS = {"actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/cache": "55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
        "actions/setup-python": "6d4fd22b20465ccc0f7354476588e8df7c9ca0e0", "actions/setup-node": "949feb2413d6458794dcd2491c4babbbce0c15c1",
        "actions/setup-dotnet": "0f4a354dd5547a28c70b7853dbd95d5b67886e73"}


def load(p):
    return yaml.safe_load(p.read_text())


def triggers(doc):
    return doc.get("on", doc.get(True))                     # PyYAML reads the bare key `on` as boolean True


def steps(doc):
    if "runs" in doc:
        return doc["runs"]["steps"]
    return [s for j in doc["jobs"].values() for s in j["steps"]]


def uses_refs(doc):
    return [s["uses"] for s in steps(doc) if "uses" in s]


@pytest.mark.parametrize("p", [*FILES.values(), ACTION], ids=lambda p: p.name)
def test_every_remote_action_is_pinned_by_full_commit_sha(p):
    for u in uses_refs(load(p)):
        name, _, ref = u.partition("@")
        if name.startswith("OWNER/"):
            assert ref == "<FULL_COMMIT_SHA>", "the cdi action is a clearly marked TODO until a release commit exists"
            assert "TODO" in p.read_text()
            continue
        assert SHA.match(ref), f"{u} is not pinned by a full commit SHA"
        base = "/".join(name.split("/")[:2])
        assert PINS[base] == ref, f"{u} does not match the verified pin"


@pytest.mark.parametrize("p", [*FILES.values(), ACTION], ids=lambda p: p.name)
def test_pins_carry_a_version_comment(p):
    for line in p.read_text().splitlines():
        if re.search(r"uses: actions/", line):
            assert re.search(r"# v\d+\.\d+\.\d+$", line.strip()), line


def test_no_pull_request_target_anywhere():
    for p in [*FILES.values(), ACTION, *(ROOT / ".github").rglob("*.yml")]:
        d = load(p)
        assert "pull_request_target" not in (triggers(d) or {}) if "jobs" in d else True, p
        assert "pull_request_target" not in yaml.safe_dump(d), p        # comments are not parsed, so a documented 'never' does not trip this


def test_pr_workflow_trigger_permissions_and_fork_guard():
    d = load(FILES["pr"])
    t = triggers(d)
    assert set(t) == {"pull_request"} and t["pull_request"]["types"] == ["opened", "synchronize", "reopened"]
    assert d["permissions"] == {"contents": "read", "pull-requests": "write", "statuses": "write"}, "no permission beyond these three"
    job = d["jobs"]["impact"]
    assert "permissions" not in job and "head.repo.full_name == github.repository" in job["if"]
    assert d["concurrency"]["cancel-in-progress"] is True


def test_pr_workflow_reads_the_base_revision_and_only_restores_the_cache():
    d = load(FILES["pr"])
    st = steps(d)
    co = next(s for s in st if s["uses"].startswith("actions/checkout@"))
    assert co["with"]["ref"] == "${{ github.event.pull_request.base.sha }}" and co["with"]["persist-credentials"] is False
    assert all(not s["uses"].startswith("actions/cache@") and "/save@" not in s["uses"] for s in st if "uses" in s), "a PR run must not be able to save a cache"
    assert any(s["uses"].startswith("actions/cache/restore@") for s in st)
    assert not any("run" in s for s in st), "the PR workflow runs no inline shell: nothing from the PR can reach one"


def test_baseline_workflow_runs_only_on_push_to_the_base_branch_and_saves():
    d = load(FILES["baseline"])
    t = triggers(d)
    assert set(t) == {"push"} and t["push"] == {"branches": ["main"]}
    assert d["permissions"] == {"contents": "read"}
    assert any(s["uses"].startswith("actions/cache/save@") for s in steps(d))


def test_workflow_base_branch_matches_the_example_config():
    cfg = yaml.safe_load((ROOT / "config.example/config.yml").read_text())
    assert triggers(load(FILES["baseline"]))["push"]["branches"] == [cfg["branches"]["base"]]


def test_cache_keys_include_the_store_schema_version():
    from cdi.store import SCHEMA_VERSION
    for p in FILES.values():
        assert f"cdi-baseline-v{SCHEMA_VERSION}-" in p.read_text()


UNTRUSTED = re.compile(r"github\.(head_ref|event\.pull_request\.(title|body|head\.ref|head\.label)|event\.(comment|issue|review)\.body|event\.head_commit\.message)")


@pytest.mark.parametrize("p", [*FILES.values(), ACTION], ids=lambda p: p.name)
def test_no_untrusted_context_is_used_anywhere(p):
    """Titles, branch names, bodies and commit messages are attacker-controlled: none may appear in any expression of these files."""
    exprs = re.findall(r"\$\{\{(.*?)\}\}", p.read_text())
    assert exprs and not [e for e in exprs if UNTRUSTED.search(e)], [e for e in exprs if UNTRUSTED.search(e)]


def test_composite_action_shape():
    d = load(ACTION)
    assert d["runs"]["using"] == "composite"
    for s in d["runs"]["steps"]:
        if "run" in s:
            assert s.get("shell") == "bash"
            assert "${{" not in s["run"], "inputs reach scripts only through env variables"
    assert {"mode", "baseline-path"} <= {k for k, v in d["inputs"].items() if v.get("required")}
    run = next(s for s in d["runs"]["steps"] if s.get("name") == "Run cdi")
    assert run["env"]["MODE"] == "${{ inputs.mode }}" and run["env"]["GITHUB_TOKEN"] == "${{ github.token }}"
    install = next(s for s in d["runs"]["steps"] if s.get("name", "").startswith("Install"))
    assert "github.action_path" in install["env"]["TOOL"], "the tool comes from the pinned action ref"


def test_the_action_never_saves_a_cache():
    assert not any("actions/cache" in u for u in uses_refs(load(ACTION)))
