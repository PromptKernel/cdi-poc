"""Map changed hunks to graph nodes.
  old side of a hunk  -> BASELINE node locations   (finds what was modified or deleted, including pure deletions inside a modified file)
  new side of a hunk  -> OVERLAY  node locations   (finds what was modified or added)
A changed, scanned file with no overlapping node is reported as 'no graph node', never dropped."""
from __future__ import annotations
import dataclasses


def overlaps(node, rng):
    loc = node.get("location")
    return bool(loc and rng and loc["line"] <= rng[1] and (loc.get("end_line") or loc["line"]) >= rng[0])


@dataclasses.dataclass
class Mapped:
    node: dict
    change: str            # added | modified | removed
    file: str
    sides: list            # which hunk sides hit it: 'old', 'new', 'file'


def map_file(change, baseline_nodes, overlay_nodes, excluded_kinds=()):
    """change: impact.diff.FileChange; baseline_nodes / overlay_nodes: nodes declared in this file (dicts). Returns (list[Mapped], reason|None)."""
    base = {n["id"]: n for n in baseline_nodes if n["kind"] not in excluded_kinds}
    over = {n["id"]: n for n in overlay_nodes if n["kind"] not in excluded_kinds}
    hits: dict[str, set] = {}
    if change.status == "D":
        for i in base:
            hits.setdefault(i, set()).add("file")
    elif change.status == "A":
        for i in over:
            hits.setdefault(i, set()).add("file")
    else:
        for h in change.hunks:
            for i, n in base.items():
                if overlaps(n, h.old_range):
                    hits.setdefault(i, set()).add("old")
            for i, n in over.items():
                if overlaps(n, h.new_range):
                    hits.setdefault(i, set()).add("new")
    out = []
    for i, sides in sorted(hits.items()):
        in_b, in_o = i in base, i in over
        kind = "modified" if in_b and in_o else "removed" if in_b else "added"
        if change.status == "D":
            kind = "removed"
        elif change.status == "A":
            kind = "added"
        out.append(Mapped(base.get(i) or over[i], kind, change.path, sorted(sides)))
    reason = None if out else "no graph node: the changed lines are not inside any node declared by the scanner (e.g. imports, comments, whitespace, or code the scanner does not model)"
    return out, reason
