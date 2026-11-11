#!/usr/bin/env python3
"""Compare scanner output with the hand-written tests/expected_edges.yml.
usage: compare_expected.py [graph_dir=out/graph] [expected=tests/expected_edges.yml]
Exit code 1 if any expected edge is missing, any 'absent' guard is violated, or a test-node annotation differs.
Recall is measured on SYNTHETIC data (see header of expected_edges.yml)."""
import json, sys, pathlib, collections, re, yaml

def load(graph_dir):
    return {p.stem: json.loads(p.read_text()) for p in pathlib.Path(graph_dir).glob("*.json") if p.stem in ("web", "api", "db")}

def compare(graphs, spec):
    al = spec.get("aliases", {})
    def ex(s):  # expand every $ALIAS occurrence (also inside parameter lists)
        return re.sub(r"\$([A-Za-z]+)", lambda m: al[m.group(1)], s) if s else s
    idx = {}
    for r, g in graphs.items():
        nodes = {n["id"]: n for n in g["nodes"]}
        idx[r] = [(e, nodes.get(e["source"]), nodes.get(e["target"])) for e in g["edges"]]
    def match(exp, e, s, t):
        if e["type"] != exp["type"]: return False
        if "source" in exp and (s is None or s["name"] != ex(exp["source"])): return False
        if "target" in exp and (t is None or t["name"] != ex(exp["target"])): return False
        if "target_kind" in exp and (t is None or t["kind"] != exp["target_kind"]): return False
        if "target_contains" in exp and exp["target_contains"] not in e["target"]: return False
        if "file" in exp and e["source_file"] != exp["file"]: return False
        if "line" in exp and e["location"]["line"] != exp["line"]: return False
        if "confidence" in exp and e["confidence"] != exp["confidence"]: return False
        return True
    res = {"missing": [], "matched": 0, "total": 0, "by_type": collections.defaultdict(lambda: [0, 0]),
           "violations": [], "test_mismatch": [], "unexpected": collections.Counter(), "matched_ids": set()}
    for exp in spec["edges"]:
        res["total"] += 1; res["by_type"][exp["type"]][1] += 1
        hit = next(((e["id"]) for e, s, t in idx.get(exp["repo"], []) if match(exp, e, s, t)), None)
        if hit: res["matched"] += 1; res["by_type"][exp["type"]][0] += 1; res["matched_ids"].add(hit)
        else: res["missing"].append(exp)
    for g in spec.get("absent", []):
        for e, s, t in idx.get(g["repo"], []):
            if match(g, e, s, t): res["violations"].append((g, e["id"]))
    for tst in spec.get("tests", []):
        n = next((n for n in graphs[tst["repo"]]["nodes"] if n["kind"] == "TEST" and n["name"] == tst["name"]), None)
        got = sorted((n or {}).get("attrs", {}).get("covers_annotation", [])) if n else None
        if n is None or got != sorted(tst["covers"]): res["test_mismatch"].append((tst, got))
    for r, lst in idx.items():
        for e, s, t in lst:
            if e["id"] not in res["matched_ids"]: res["unexpected"][(r, e["type"])] += 1
    return res

def report(res):
    rec = res["matched"] / res["total"] if res["total"] else 0
    lines = [f"expected edges: {res['total']}  matched: {res['matched']}  recall: {rec:.1%}  (SYNTHETIC sample, hand-written expectations)"]
    for t, (m, n) in sorted(res["by_type"].items()): lines.append(f"  {t:<22} {m}/{n}")
    lines.append(f"absent-guard violations: {len(res['violations'])}   test-annotation mismatches: {len(res['test_mismatch'])}")
    extra = sum(res["unexpected"].values())
    lines.append(f"scanner edges not listed in expected file (not failures, listed for review): {extra} {dict(res['unexpected'])}")
    for m in res["missing"]: lines.append(f"  MISSING: {m}")
    for g, i in res["violations"]: lines.append(f"  VIOLATION: {g.get('why')} -> {i}")
    for t, got in res["test_mismatch"]: lines.append(f"  TEST MISMATCH: {t['name']} expected {t['covers']} got {got}")
    return "\n".join(lines), rec

if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parents[1]
    gd = sys.argv[1] if len(sys.argv) > 1 else root / "out/graph"
    sp = sys.argv[2] if len(sys.argv) > 2 else root / "tests/expected_edges.yml"
    res = compare(load(gd), yaml.safe_load(pathlib.Path(sp).read_text()))
    text, rec = report(res); print(text)
    sys.exit(0 if not (res["missing"] or res["violations"] or res["test_mismatch"]) else 1)
