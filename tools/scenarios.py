#!/usr/bin/env python3
"""Synthetic PR scenarios for the impact engine demo and tests. Each scenario is ONE commit on a local branch off `main` (never pushed).
usage: python tools/scenarios.py [--base main] [--prefix ""]   creates the local branches (existing ones are re-pointed with `-B`; they hold only these commits)
Worktrees are created at named paths under out/work and removed again with `git worktree remove` on exactly those paths."""
import argparse, pathlib, subprocess, sys

SCENARIOS = {
    # a) change the body of dbo.spGetAllEmployees
    "pr-a-sp-body": {"samples/db/synthetic/procedures/spGetAllEmployees.sql":
                     lambda t: t.replace("    ORDER BY EmployeeID;", "    WHERE Name <> ''\n    ORDER BY EmployeeID;")},
    # b) change dbo.vwEmployeeDepartment (synthetic view)
    "pr-b-view": {"samples/db/synthetic/views/vwEmployeeDepartment.sql":
                  lambda t: t.replace("SELECT e.EmployeeID, e.Name,", "SELECT e.EmployeeID, d.DepartmentID, e.Name,")},
    # c) change the TypeScript service method that calls api/Employee/Index
    "pr-c-ts-service": {"samples/web/src/app/services/employee.service.ts":
                        lambda t: t.replace("  getEmployees() {\n", "  getEmployees() {\n    console.log('loading employees');\n")},
    # d) change a synthetic file that contains dynamic SQL
    "pr-d-dynamic-sql": {"samples/db/synthetic/procedures/spSearchEmployees.sql":
                         lambda t: t.replace("SELECT EmployeeID, Name FROM dbo.tblEmployee WHERE ", "SELECT TOP 50 EmployeeID, Name FROM dbo.tblEmployee WHERE ")},
    # e) delete the synthetic spGetDepartmentHeadcount
    "pr-e-delete-proc": {"samples/db/synthetic/procedures/spGetDepartmentHeadcount.sql": None},
    # f) change a controller route template so the frontend request no longer matches
    "pr-f-route": {"samples/api/Controllers/EmployeeController.cs": lambda t: t.replace('[Route("Index")]', '[Route("List")]', 1)},
}


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


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="main"); a = ap.parse_args()
    for b, e in SCENARIOS.items():
        make_branch(".", b, e, a.base)
        print("created local branch", b, git(".", "rev-parse", "--short", b))
