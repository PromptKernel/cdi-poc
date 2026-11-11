"""Deterministic blocking policies. A policy fires only on a stored, evidenced fact about the PR (an UNRESOLVED link INTRODUCED by it), never on a risk label.
Every violation carries file:line, analysis method and commit. A deliberate rename or deletion of an object can trigger these (see docs/ci-simulation.md)."""
from __future__ import annotations

KNOWN = {}


def policy(pid):
    def deco(fn):
        KNOWN[pid] = fn
        return fn
    return deco


def _violation(pid, u, what):
    return {"policy": pid, "message": what, "repo": u["repo"], "file": u["file"], "line": u["line"], "method": u["method"], "commit": u["commit"],
            "evidence": u.get("evidence", ""), "reason": u.get("reason"), "edge_type": u["type"], "synthetic": u.get("synthetic", False)}


@policy("P1-referenced-not-found-introduced")
def referenced_not_found(result):
    out = []
    for u in result["new_unresolved"]:
        if (u["type"] == "RESOLVES_TO" and u.get("target_cause") == "referenced_not_found") or \
           (u["confidence"] == "UNRESOLVED" and u.get("target_kind") == "SQL_REF"):
            out.append(_violation("P1-referenced-not-found-introduced", u, f"`{u['source_node']}` is referenced but no definition was found"))
    return out


@policy("P2-route-unmatched-introduced")
def route_unmatched(result):
    return [_violation("P2-route-unmatched-introduced", u, f"request `{u['source_node']}` no longer matches any API route")
            for u in result["new_unresolved"] if u["type"] == "ROUTES_TO" and u.get("target_cause") == "no_matching_route"]


def evaluate(result, enabled_ids):
    unknown = [p for p in enabled_ids if p not in KNOWN]
    if unknown:
        raise ValueError(f"unknown blocking policy ids in config/ci.yml: {unknown}; known: {sorted(KNOWN)}")
    return [v for pid in enabled_ids for v in KNOWN[pid](result)]
