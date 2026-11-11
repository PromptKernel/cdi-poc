#!/usr/bin/env python3
"""Synthetic PR scenarios for the impact engine demo, tests and evaluation. Each scenario is ONE commit on a local branch off the base branch
(never pushed). Scenarios are defined by the target repository in `.cdi/scenarios.yml`; nothing about any sample lives in this module.
usage: python -m cdi.eval.scenarios [--base <branch>] [--file .cdi/scenarios.yml]   creates the local branches (existing ones are re-pointed with `-B`)
Worktrees are created at named paths under out/work and removed again with `git worktree remove` on exactly those paths."""
import argparse, pathlib, subprocess
import yaml

DEFAULT_FILE = ".cdi/scenarios.yml"


def _edit(spec):
    if spec.get("delete"):
        return None
    old, new, count = spec["old"], spec["new"], spec.get("count", -1)
    return lambda t: t.replace(old, new, count)


def load_scenarios(path=DEFAULT_FILE):
    """name -> {relative path: callable(text)->text | None (delete)}. Several edits of one file are chained."""
    out = {}
    for name, sc in (yaml.safe_load(pathlib.Path(path).read_text()) or {}).get("scenarios", {}).items():
        edits = {}
        for spec in sc["edits"]:
            fn, prev = _edit(spec), edits.get(spec["path"])
            edits[spec["path"]] = fn if prev is None or fn is None else (lambda t, a=prev, b=fn: b(a(t)))
        out[name] = edits
    return out


def git(repo, *a, ident=()):
    r = subprocess.run(["git", *ident, "-C", str(repo), *a], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout.strip()


def make_branch(repo, branch, edits, base="main", workdir=None, ident=()):
    repo = pathlib.Path(repo)
    wt = pathlib.Path(workdir or repo / "out/work") / f"wt-{branch}"
    git(repo, "worktree", "add", "-q", "-B", branch, str(wt), base)
    try:
        for rel, fn in edits.items():
            if fn is None:
                git(wt, "rm", "-q", rel)
            else:
                f = wt / rel
                new = fn(f.read_text())
                assert new != f.read_text(), f"scenario edit for {rel} changed nothing"
                f.write_text(new)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", f"scenario {branch} (synthetic, local only)", ident=ident)
    finally:
        git(repo, "worktree", "remove", "--force", str(wt))
    return branch


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None, help="base branch (default: branches.base from .cdi/config.yml)"); ap.add_argument("--file", default=DEFAULT_FILE); ap.add_argument("--names", nargs="*")
    a = ap.parse_args(argv)
    if not a.base:
        from cdi.linker.graphio import load_config
        a.base = load_config()["branches"]["base"]
    for b, e in load_scenarios(a.file).items():
        if a.names and b not in a.names:
            continue
        make_branch(".", b, e, a.base)
        print("created local branch", b, git(".", "rev-parse", "--short", b))


if __name__ == "__main__":
    main()
