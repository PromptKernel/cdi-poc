"""scripts/prepush_gate.sh and .githooks/pre-commit, exercised on throw-away git repositories. Nothing here contains a real name, path or credential:
the private term is a made-up word and credential-looking strings are assembled at run time."""
import os, pathlib, shutil, subprocess
import pytest
from conftest import ROOT

GATE = ROOT / "scripts" / "prepush_gate.sh"
HOOK = ROOT / ".githooks" / "pre-commit"
TERM = "sekrit-term-xyz"
GITLEAKS = shutil.which("gitleaks")
ENV_BASE = {"PATH": f"/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1", "HOME": "/nonexistent-home-for-tests"}


def git(cwd, *a, env=None, check=True):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=check, env={**ENV_BASE, **(env or {})})


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    git(r, "init", "-q", "-b", "main"); git(r, "config", "user.email", "dev@example.invalid"); git(r, "config", "user.name", "dev"); git(r, "config", "commit.gpgsign", "false")
    (r / "a.txt").write_text("hello\n")
    git(r, "add", "a.txt"); git(r, "commit", "-q", "-m", "init")
    (tmp_path / "terms.txt").write_text(f"# private terms\n{TERM}\n")
    return r


def gate(r, *args, env=None, conf=None, terms=True):
    e = {**ENV_BASE, "PREPUSH_TERMS_FILE": str(r.parent / "terms.txt") if terms else "", "PREPUSH_OVERLAP_FILE": "", **(env or {})}
    if not GITLEAKS:
        e.setdefault("PREPUSH_ALLOW_NO_GITLEAKS", "1")
    else:
        e["PATH"] = e["PATH"]
    a = [str(GATE), *args] + (["--conf", str(conf)] if conf else [])
    return subprocess.run(a, cwd=r, capture_output=True, text=True, env=e)


def commit(r, msg="change", env=None):
    return git(r, "commit", "-q", "-m", msg, env=env)


def add_file(r, name, content="x\n", binary=False):
    p = r / name; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content if binary else content.encode())
    git(r, "add", "--", name)


SEP = "/"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16


def test_a_clean_tree_passes_and_says_what_it_checked(repo):
    res = gate(repo)
    assert res.returncode == 0 and "GATE PASSED" in res.stdout and "commits to be pushed:" in res.stdout and "images: png jpg jpeg gif webp" in res.stdout
    assert "overlap check was NOT run" in res.stdout, "a skipped check is reported, not silent"


@pytest.mark.parametrize("name", ["shot.png", "deep/dir/shot.PNG", "x.jpg", "x.jpeg", "x.gif", "x.webp"])
def test_a_staged_image_fails_the_gate(repo, name):
    add_file(repo, name, PNG, binary=True)                                 # staged, not committed
    res = gate(repo)
    assert res.returncode == 1 and "GATE FAIL [images]" in res.stdout and name in res.stdout and "GATE FAILED" in res.stdout and "[images]" in res.stdout.splitlines()[-1]


def test_a_committed_image_fails_and_so_does_one_added_and_removed_inside_the_range(repo):
    add_file(repo, "shot.png", PNG, binary=True); commit(repo, "add image")
    assert gate(repo).returncode == 1
    git(repo, "rm", "-q", "shot.png"); commit(repo, "remove image")
    res = gate(repo, "--range", "HEAD~2..HEAD")                            # both commits will be pushed: the image is in the pushed history
    assert res.returncode == 1 and "shot.png" in res.stdout


def test_an_image_that_was_already_pushed_and_then_removed_does_not_block_the_removal_commit(repo, tmp_path):
    add_file(repo, "shot.png", PNG, binary=True); commit(repo, "add image")
    bare = tmp_path / "remote.git"; subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare)); git(repo, "push", "-q", "origin", "main")
    git(repo, "rm", "-q", "--cached", "shot.png"); commit(repo, "stop tracking the image")
    res = gate(repo)                                                       # range = what is not on the remote: only the removal
    assert res.returncode == 0 and "commits to be pushed: 1" in res.stdout


def test_images_are_allowed_only_in_allowlisted_folders(repo):
    add_file(repo, "assets/logo.png", PNG, binary=True); add_file(repo, "other/x.png", PNG, binary=True)
    res = gate(repo, env={"PREPUSH_ALLOW_IMAGE_DIRS": "assets"})
    assert res.returncode == 1 and "other/x.png" in res.stdout and "assets/logo.png" not in res.stdout
    git(repo, "rm", "-q", "--cached", "other/x.png"); (repo / "other/x.png").unlink()
    assert gate(repo, env={"PREPUSH_ALLOW_IMAGE_DIRS": "assets"}).returncode == 0
    add_file(repo, "png.txt", "not an image\n")
    assert gate(repo, env={"PREPUSH_ALLOW_IMAGE_DIRS": "assets"}).returncode == 0, "the extension decides, not the word 'png'"


def test_every_hit_is_printed_nothing_is_hidden(repo):
    for i in range(4):
        add_file(repo, f"s{i}.png", PNG, binary=True)
    out = gate(repo).stdout
    assert out.count("GATE FAIL [images]") == 4 and all(f"s{i}.png" in out for i in range(4)) and "4 hit(s)" in out


def test_forbidden_paths_fail(repo):
    add_file(repo, "docs/screenshots/notes.txt", "x\n")
    res = gate(repo, env={"PREPUSH_FORBIDDEN_PATHS": "docs/screenshots private/ out/"})
    assert res.returncode == 1 and "GATE FAIL [paths]: forbidden path (docs/screenshots): docs/screenshots/notes.txt" in res.stdout


def test_private_names_are_found_in_content_messages_and_author_fields(repo):
    add_file(repo, "n.txt", f"written by {TERM}\n"); commit(repo, "ok message")
    res = gate(repo, "--range", "HEAD~1..HEAD")
    assert res.returncode == 1 and "GATE FAIL [names]" in res.stdout and "n.txt" in res.stdout
    git(repo, "rm", "-q", "n.txt"); commit(repo, f"mentions {TERM} in the message")
    res = gate(repo, "--range", "HEAD~1..HEAD")
    assert res.returncode == 1 and "commit message or author field" in res.stdout


def test_a_missing_terms_file_fails_unless_explicitly_waived(repo):
    res = gate(repo, terms=False)
    assert res.returncode == 1 and "GATE FAIL [names]" in res.stdout and "no private-terms file" in res.stdout
    res = gate(repo, terms=False, env={"PREPUSH_ALLOW_MISSING_TERMS": "1"})
    assert res.returncode == 0 and "private-name search was NOT run" in res.stdout


def test_home_directory_paths_fail_but_relative_paths_do_not(repo):
    add_file(repo, "ok.ts", "import { Home } from './home/home.component';\nconst f = 'src/app/home/x.ts';\n")
    assert gate(repo).returncode == 0
    add_file(repo, "bad.txt", f"see {SEP}Users{SEP}someone{SEP}project{SEP}file\n")      # assembled at run time: no literal home path sits in this file
    res = gate(repo)
    assert res.returncode == 1 and "GATE FAIL [paths]" in res.stdout and "bad.txt" in res.stdout
    git(repo, "rm", "-q", "-f", "bad.txt"); add_file(repo, "bad2.txt", f"at {SEP}home{SEP}someone{SEP}x\n")
    assert gate(repo).returncode == 1


def test_this_machines_own_home_directory_is_detected(repo):
    fake_home = "/srv/someone-unusual-home"
    add_file(repo, "p.txt", f"log at {fake_home}/x\n")
    res = gate(repo, env={"HOME": fake_home})
    assert res.returncode == 1 and "this machine's own path or login name" in res.stdout and "p.txt" in res.stdout


def test_credential_patterns_fail(repo):
    add_file(repo, "c.txt", "token = gh" + "p_" + "A1b2C3d4E5" * 4 + "\n")
    res = gate(repo)
    assert res.returncode == 1 and "GATE FAIL [credentials]" in res.stdout and "c.txt" in res.stdout
    git(repo, "rm", "-q", "-f", "c.txt"); add_file(repo, "k.txt", "-----BEGIN " + "RSA PRIVATE KEY-----\n")
    assert gate(repo).returncode == 1


def test_unexpected_author_or_committer_email_fails_and_the_rule_is_configurable(repo):
    add_file(repo, "b.txt", "b\n"); git(repo, "commit", "-q", "-m", "other person", "--author", "Other <other@example.invalid>")
    res = gate(repo, "--range", "HEAD~1..HEAD")
    assert res.returncode == 1 and "GATE FAIL [authors]" in res.stdout and "other@example.invalid" in res.stdout
    ok = gate(repo, "--range", "HEAD~1..HEAD", env={"PREPUSH_ALLOWED_EMAIL_REGEX": r"@example\.invalid$"})
    assert ok.returncode == 0


def test_rules_file_is_parsed_not_executed_and_unknown_keys_are_rejected(repo, tmp_path):
    marker = tmp_path / "pwned"
    conf = tmp_path / "rules.conf"
    conf.write_text(f'FORBIDDEN_PATHS="$(touch {marker})"\nIMAGE_EXTENSIONS="png"\n')
    res = gate(repo, conf=conf)
    assert not marker.exists(), "a rules file must never be executed"
    conf.write_text("NOT_A_KEY=1\n")
    res = gate(repo, conf=conf)
    assert res.returncode == 1 and "unknown key 'NOT_A_KEY'" in res.stdout
    assert gate(repo, conf=tmp_path / "missing.conf").returncode == 1


def test_gitleaks_missing_fails_unless_waived(repo):
    e = {"PATH": "/usr/bin:/bin"}
    if shutil.which("gitleaks", path=e["PATH"]):
        pytest.skip("gitleaks is installed in a system path")
    res = subprocess.run([str(GATE)], cwd=repo, capture_output=True, text=True, env={**ENV_BASE, **e, "PREPUSH_TERMS_FILE": str(repo.parent / "terms.txt")})
    assert res.returncode == 1 and "GATE FAIL [gitleaks]" in res.stdout and "not installed" in res.stdout
    res = subprocess.run([str(GATE)], cwd=repo, capture_output=True, text=True, env={**ENV_BASE, **e, "PREPUSH_TERMS_FILE": str(repo.parent / "terms.txt"), "PREPUSH_ALLOW_NO_GITLEAKS": "1"})
    assert res.returncode == 0 and "that check was NOT run" in res.stdout


@pytest.mark.skipif(not GITLEAKS, reason="gitleaks not installed")
def test_gitleaks_runs_over_the_commits_to_be_pushed(repo):
    res = gate(repo)
    assert res.returncode == 0 and "gitleaks (commits to be pushed)" in res.stdout


def test_overlap_with_a_private_text_is_detected_when_configured(repo, tmp_path):
    src = tmp_path / "private.txt"; src.write_text("the quick brown fox jumps over the lazy dog every single morning\n")
    add_file(repo, "o.txt", "Note: the quick brown fox jumps over a fence\n")
    res = gate(repo, env={"PREPUSH_OVERLAP_FILE": str(src)})
    assert res.returncode == 1 and "GATE FAIL [overlap]" in res.stdout and "the quick brown fox jumps" in res.stdout
    assert gate(repo, env={"PREPUSH_OVERLAP_FILE": str(src), "PREPUSH_OVERLAP_WORDS": "9"}).returncode == 0


# ---- the pre-commit hook --------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def hooked(repo):
    (repo / ".githooks").mkdir(); shutil.copy(HOOK, repo / ".githooks/pre-commit")
    git(repo, "config", "core.hooksPath", ".githooks")
    return repo


def test_the_hook_rejects_staged_images_and_keeps_the_file(hooked):
    add_file(hooked, "shot.png", PNG, binary=True)
    r = git(hooked, "commit", "-q", "-m", "oops", check=False)
    assert r.returncode != 0 and "image file staged: shot.png" in r.stderr and "commit rejected" in r.stderr
    assert (hooked / "shot.png").exists() and git(hooked, "log", "--oneline").stdout.count("\n") == 1, "nothing was committed, the file is untouched"


def test_the_hook_allows_ordinary_commits_and_allowlisted_image_folders(hooked):
    add_file(hooked, "b.txt", "b\n")
    assert git(hooked, "commit", "-q", "-m", "fine", check=False).returncode == 0
    add_file(hooked, "assets/a.png", PNG, binary=True)
    assert git(hooked, "commit", "-q", "-m", "img", check=False).returncode != 0
    assert git(hooked, "commit", "-q", "-m", "img", check=False, env={"PREPUSH_ALLOW_IMAGE_DIRS": "assets"}).returncode == 0


def test_the_hook_reads_forbidden_paths_from_the_rules_file(hooked):
    (hooked / ".prepush-gate.conf").write_text('FORBIDDEN_PATHS="private/ docs/screenshots"\n')
    add_file(hooked, "docs/screenshots/readme.txt", "x\n")
    r = git(hooked, "commit", "-q", "-m", "x", check=False)
    assert r.returncode != 0 and "forbidden path staged (docs/screenshots)" in r.stderr


# ---- the scripts themselves ---------------------------------------------------------------------------------------------------------------
def test_scripts_never_hide_output_and_nothing_is_hardcoded():
    for f in (GATE, HOOK):
        text = f.read_text()
        assert "grep -v" not in text and "grep -Ev" not in text and "| head" not in text and "| tail" not in text, f.name
    conf = (ROOT / ".prepush-gate.conf").read_text()
    assert "noreply" not in conf and "@" not in conf, "no identity in the rules file"
    terms_file = ROOT / "private" / "prepush-terms.txt"                       # the real private terms, when this checkout has them; never copied into the repository
    if terms_file.exists():
        import re
        for term in [t for t in terms_file.read_text().splitlines() if t.strip() and not t.startswith("#")]:
            assert not re.search(term, conf, re.I), "private names live only in the git-ignored terms file"


def test_docs_say_pushes_are_one_command_joined_by_and_and():
    doc = (ROOT / "docs/pre-push-gate.md").read_text()
    assert "scripts/prepush_gate.sh && git push" in doc and "never" in doc.lower() and "git config core.hooksPath .githooks" in doc


def test_commits_already_on_the_remote_are_not_rescanned_but_new_ones_and_the_tree_always_are(repo, tmp_path):
    """Merging an already-pushed branch into main publishes nothing new: its commits are on the remote. Anything not yet on the remote is scanned in full."""
    bare = tmp_path / "remote.git"; subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare)); git(repo, "push", "-q", "origin", "main")
    git(repo, "switch", "-q", "-c", "feature")
    add_file(repo, "shot.png", PNG, binary=True); commit(repo, "add image on the feature branch")
    git(repo, "rm", "-q", "shot.png"); commit(repo, "remove it again")
    git(repo, "push", "-q", "-u", "origin", "feature")                                     # the image is now public on origin/feature
    git(repo, "switch", "-q", "main"); git(repo, "branch", "-q", "--set-upstream-to=origin/main", "main"); git(repo, "merge", "-q", "--ff-only", "feature")
    res = gate(repo)
    assert res.returncode == 0 and "commits to be pushed: 0" in res.stdout and "already on remote 'origin'" in res.stdout, res.stdout
    add_file(repo, "second.png", PNG, binary=True); commit(repo, "a NEW image commit")      # not on the remote: scanned
    res = gate(repo)
    assert res.returncode == 1 and "second.png" in res.stdout
    git(repo, "rm", "-q", "second.png"); commit(repo, "remove the new image")
    assert gate(repo).returncode == 1, "the new commit that added the image is still in the range, even though a later commit removed it"
    # the tree is always scanned: an image still tracked fails even when every commit is already public
    git(repo, "reset", "-q", "--hard", "origin/feature")
    git(repo, "switch", "-q", "-c", "other"); add_file(repo, "tracked.png", PNG, binary=True); commit(repo, "track an image")
    git(repo, "push", "-q", "-u", "origin", "other")
    res = gate(repo)
    assert res.returncode == 1 and "tracked.png" in res.stdout
