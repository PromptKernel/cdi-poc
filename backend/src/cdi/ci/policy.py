"""Deterministic blocking policies. A policy fires only on a stored, evidenced fact about the PR (an UNRESOLVED link INTRODUCED by it), never on a risk label.
Every violation carries file:line, analysis method and commit. A deliberate rename or deletion of an object can trigger these (see docs/ci-simulation.md)."""
from __future__ import annotations

KNOWN = {}


def policy(pid):
    def deco(fn):
        KNOWN[pid] = fn
        return fn
    return deco


def _violation(pid, u, what, missing):
    return {"policy": pid, "message": what, "missing_object": missing, "repo": u["repo"], "file": u["file"], "line": u["line"], "method": u["method"],
            "commit": u["commit"], "evidence": u.get("evidence", ""), "reason": u.get("reason"), "edge_type": u["type"],
            "synthetic": u.get("synthetic", False), "referenced_from": list((u.get("attrs") or {}).get("referenced_from", []))}


@policy("P1-referenced-not-found-introduced")
def referenced_not_found(result):
    out = []
    for u in result["new_unresolved"]:
        if (u["type"] == "RESOLVES_TO" and u.get("target_cause") == "referenced_not_found") or \
           (u["confidence"] == "UNRESOLVED" and u.get("target_kind") == "SQL_REF"):
            # the MISSING object: the reference node's name (RESOLVES_TO source) or the undefined target of a scanner-level reference
            missing = u["source_node"] if u["type"] == "RESOLVES_TO" else u["target"]
            out.append(_violation("P1-referenced-not-found-introduced", u, f"`{missing}` is referenced but no definition was found", missing))
    return out


@policy("P2-route-unmatched-introduced")
def route_unmatched(result):
    return [_violation("P2-route-unmatched-introduced", u, f"request `{u['source_node']}` no longer matches any API route", u["source_node"])
            for u in result["new_unresolved"] if u["type"] == "ROUTES_TO" and u.get("target_cause") == "no_matching_route"]


def evaluate(result, enabled_ids):
    unknown = [p for p in enabled_ids if p not in KNOWN]
    if unknown:
        raise ValueError(f"unknown blocking policy ids in config/ci.yml: {unknown}; known: {sorted(KNOWN)}")
    return [v for pid in enabled_ids for v in KNOWN[pid](result)]


def _parse_site(text):
    """'repo:path/to/file.cs:24' -> (repo, file, line)"""
    repo, rest = text.split(":", 1)
    file, line = rest.rsplit(":", 1)
    return repo, file, int(line)


def group(violations):
    """Group hits by (policy, missing object): one deleted procedure is ONE item, with every location (reference site) listed under it.
    Locations are de-duplicated by repo:file:line; the analysis methods and commits that evidence each are merged."""
    groups = {}
    for v in violations:
        g = groups.setdefault((v["policy"], v["missing_object"].lower()),
                              {"policy": v["policy"], "missing_object": v["missing_object"], "message": v["message"], "reasons": [], "locations": {}})
        if v.get("reason") and v["reason"] not in g["reasons"]:
            g["reasons"].append(v["reason"])
        loc = g["locations"].setdefault((v["repo"], v["file"], v["line"]), {"repo": v["repo"], "file": v["file"], "line": v["line"],
                                                                         "methods": [], "commits": [], "edge_types": [], "evidence": ""})
        for key, val in (("methods", v["method"]), ("commits", v["commit"]), ("edge_types", v["edge_type"])):
            if val and val not in loc[key]:
                loc[key].append(val)
        loc["evidence"] = loc["evidence"] or v.get("evidence", "")
        for site in v.get("referenced_from", []):          # other places that reference the same missing object
            r, f, l = _parse_site(site)
            g["locations"].setdefault((r, f, l), {"repo": r, "file": f, "line": l, "methods": [], "commits": [], "edge_types": [], "evidence": ""})
    out = []
    for g in groups.values():
        g["reasons"].sort(key=lambda r: "any scanned repo" not in r)      # prefer the cross-repo linker's wording when several reasons exist
        g["locations"] = sorted(g["locations"].values(), key=lambda x: (x["repo"], x["file"], x["line"]))
        out.append(g)
    return sorted(out, key=lambda g: (g["policy"], g["missing_object"].lower()))
