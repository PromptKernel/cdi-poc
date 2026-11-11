#!/usr/bin/env python3
"""Evidence helper: print scanner edges for one workflow and re-read the cited source line from disk for comparison.
usage: show_workflow.py <substring> [<substring> ...]   (substrings identify the workflow's nodes)"""
import json, sys, pathlib, yaml
root = pathlib.Path(__file__).resolve().parents[1]
repos = {r["name"]: r["path"] for r in yaml.safe_load((root / "config/repos.yml").read_text())["repos"]}
keys = sys.argv[1:]
for r, rpath in repos.items():
    g = json.loads((root / f"out/graph/{r}.json").read_text())
    print(f"\n=== scanner output: {r} @ {g['commit_id'][:8]} ({g['scanner']['name']}) ===")
    for e in g["edges"]:
        s, t = e["source"], e["target"]
        if not any(k in s or k in t for k in keys): continue
        loc = e["location"]
        src = (root / rpath / e["source_file"]).read_text().splitlines()[loc["line"] - 1].strip()
        print(f"{e['type']:<20} {s.split(':',2)[2][-62:]}\n{'':<20} -> {t.split(':',2)[2][-62:]}\n"
              f"{'':<20} [{e['confidence']}] {e['analysis_method']} @ {e['source_file']}:{loc['line']}:{loc.get('column')}"
              f"{' synthetic' if e['synthetic'] else ''}\n{'':<20} source line on disk: {src}")
        if "reason" in e: print(f"{'':<20} reason: {e['reason']}")
