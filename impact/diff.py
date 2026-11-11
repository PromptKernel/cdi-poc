"""Git helpers: three-dot diffs per logical repo folder, with hunk ranges for both the old and the new side."""
from __future__ import annotations
import dataclasses, re, subprocess

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def git(root, *args, check=True):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def resolve(root, rev):
    return git(root, "rev-parse", "--verify", f"{rev}^{{commit}}")


def merge_base(root, a, b):
    return git(root, "merge-base", a, b)


def folder_commit(root, rev, folder):
    """Last commit at or before `rev` that touched `folder` (same definition the scanners use for commit_id)."""
    return git(root, "log", "-1", "--format=%H", rev, "--", folder)


@dataclasses.dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int

    @property
    def old_range(self):   # (first, last) inclusive, or None for a pure addition
        return (self.old_start, self.old_start + self.old_len - 1) if self.old_len > 0 else None

    @property
    def new_range(self):   # None for a pure deletion
        return (self.new_start, self.new_start + self.new_len - 1) if self.new_len > 0 else None


@dataclasses.dataclass
class FileChange:
    path: str              # relative to the logical repo's folder
    status: str            # A | M | D
    hunks: list


def parse_diff(text: str, prefix: str):
    """Parse `git diff --no-renames -U0` output. `prefix` = repo folder + '/' (stripped from paths)."""
    changes, cur = [], None
    for line in text.splitlines():
        if line.startswith("diff --git "):
            cur = None
        elif line.startswith("+++ ") or line.startswith("--- "):
            p = line[4:].strip()
            if p == "/dev/null":
                continue
            p = p[2:] if p[:2] in ("a/", "b/") else p
            if cur is None and p.startswith(prefix):
                cur = FileChange(p[len(prefix):], "M", [])
                changes.append(cur)
        elif (m := HUNK.match(line)) and cur is not None:
            a, b, c, d = m.groups()
            cur.hunks.append(Hunk(int(a), 1 if b is None else int(b), int(c), 1 if d is None else int(d)))
    return changes


def changes(root, base, head, folder):
    """Changes between base and head (pass the merge-base as base for a three-dot diff) restricted to `folder`."""
    folder = folder.rstrip("/")
    ns = git(root, "diff", "--no-renames", "--name-status", base, head, "--", folder)
    status = {}
    for l in ns.splitlines():
        st, p = l.split("\t", 1)
        status[p[len(folder) + 1:]] = st[0]
    parsed = {c.path: c for c in parse_diff(git(root, "diff", "--no-renames", "-U0", base, head, "--", folder), folder + "/")}
    out = []
    for p, st in sorted(status.items()):
        c = parsed.get(p) or FileChange(p, st, [])
        c.status = st
        out.append(c)
    return out


def glob_re(pat: str):
    i, out = 0, ""
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"; i += 3
        elif pat.startswith("**", i):
            out += ".*"; i += 2
        elif pat[i] == "*":
            out += "[^/]*"; i += 1
        elif pat[i] == "?":
            out += "[^/]"; i += 1
        else:
            out += re.escape(pat[i]); i += 1
    return re.compile("^" + out + "$")


def is_scanned(path: str, include, exclude) -> bool:
    return any(glob_re(p).match(path) for p in include) and not any(glob_re(p).match(path) for p in exclude)
