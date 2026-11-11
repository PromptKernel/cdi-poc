#!/usr/bin/env python3
"""Validate scanner/linker output against backend/schema/graph.schema.json and check referential integrity."""
import json, sys, pathlib
from jsonschema import Draft202012Validator

from cdi.paths import SCHEMA_DIR


def main(paths=None):
    """Returns 1 when any fragment has schema errors, dangling edge endpoints or duplicate node ids, else 0."""
    paths = sys.argv[1:] if paths is None else paths
    v = Draft202012Validator(json.loads((SCHEMA_DIR / "graph.schema.json").read_text()))
    bad = 0
    frags = {p: json.loads(pathlib.Path(p).read_text()) for p in paths}
    all_ids = {n["id"] for g in frags.values() for n in g["nodes"]}   # linker output resolves against all fragments given
    for p, g in frags.items():
        errs = sorted(v.iter_errors(g), key=lambda e: list(e.path))
        ids = {n["id"] for n in g["nodes"]}
        # overlay fragments (scan restricted with --only) may point at baseline nodes outside the fragment
        scope = all_ids if g["repo"] == "linked" else ids
        dangling = [] if g.get("overlay") else [e["id"] for e in g["edges"] if e["source"] not in scope or e["target"] not in scope]
        dup_nodes = len(g["nodes"]) - len(ids)
        print(f"{p}: schema errors={len(errs)} dangling-edge-endpoints={len(dangling)} duplicate-node-ids={dup_nodes} nodes={len(g['nodes'])} edges={len(g['edges'])}")
        for e in errs[:5]: print("   ", list(e.path), e.message[:160])
        for d in dangling[:5]: print("    dangling:", d)
        bad += len(errs) + len(dangling) + dup_nodes
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
