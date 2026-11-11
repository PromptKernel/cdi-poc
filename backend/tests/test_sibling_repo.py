"""Scan the full sample repository (the sibling checkout) and compare with the pinned fixture.

Set CDI_SAMPLE_REPO to the path of a checkout of the sample repository. Skipped otherwise.
The checkout is copied (tracked files only) into a temporary git repo, so the scan reads nothing from this tool repo
and never touches the checkout itself."""
import os, pathlib, shutil
import pytest
from conftest import FIXTURE_CONFIG, FIXTURE, GIT_ID, Project, sh

SIBLING = os.environ.get("CDI_SAMPLE_REPO")
pytestmark = pytest.mark.skipif(not SIBLING or not pathlib.Path(SIBLING).is_dir(), reason="CDI_SAMPLE_REPO not set")
REPOS = ("web", "api", "db")


@pytest.fixture(scope="module")
def sibling(tmp_path_factory):
    root = tmp_path_factory.mktemp("sibling")
    shutil.copytree(FIXTURE_CONFIG, root / "config")
    repos = root / "config" / "repos.yml"
    repos.write_text(repos.read_text().replace("path: samples/", "path: "))     # the sibling has web/ api/ db/ at its root
    files = sh(["git", "ls-files", "-z"], cwd=SIBLING).stdout.split("\0")
    for f in filter(None, files):
        dst = root / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pathlib.Path(SIBLING) / f, dst)
    sh(["git", "init", "-q", "-b", "main"], cwd=root)
    sh(["git", "add", "-A"], cwd=root)
    sh(["git", *GIT_ID, "commit", "-q", "-m", "copy"], cwd=root)
    p = Project.__new__(Project)
    p.path = root
    return p


@pytest.fixture(scope="module")
def sibling_scans(sibling):
    return {r: sibling.scan(r, f"sib_{r}.json")[1] for r in REPOS}


def test_sibling_scan_reads_only_the_sibling(sibling_scans):
    sib_files = {f for f in sh(["git", "ls-files"], cwd=SIBLING).stdout.split("\n") if f}
    for r, frag in sibling_scans.items():
        seen = {n["file"] for n in frag["nodes"] if n.get("file")} | {e["source_file"] for e in frag["edges"]}
        assert seen, r
        assert all(f"{r}/{f}" in sib_files for f in seen), (r, sorted(f for f in seen if f"{r}/{f}" not in sib_files))


def test_sibling_counts_cover_the_fixture(sibling_scans, full):
    """The fixture is a subset of the sample: every fixture node and edge link exists in the full scan."""
    print("\nrepo  fixture(nodes/edges)  sibling(nodes/edges)")
    for r in REPOS:
        f, s = full[r], sibling_scans[r]
        print(f"{r:4}  {len(f['nodes']):>4}/{len(f['edges']):<4}            {len(s['nodes']):>4}/{len(s['edges']):<4}")
        assert {n["id"] for n in f["nodes"]} <= {n["id"] for n in s["nodes"]}, r
        key = lambda e: (e["type"], e["source"], e["target"], e["confidence"])
        assert {key(e) for e in f["edges"]} <= {key(e) for e in s["edges"]}, r
