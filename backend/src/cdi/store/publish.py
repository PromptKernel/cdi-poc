"""Link-and-publish helper for scripts: read the scanner and linker fragments in a folder (default out/graph), build the graph and write it to the
configured baseline store with a freshness record (per-repo commit ids from the fragments, schema version).
usage: python -m cdi.store.publish [--graph out/graph] [--store json|neo4j] [--store-path FILE] [--config .cdi/config.yml]"""
from __future__ import annotations
import argparse, json, pathlib
from cdi import store as S
from cdi.linker.graphio import Graph, load_config, load_fragments


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", default="out/graph"); ap.add_argument("--config", default=None)
    ap.add_argument("--store", default=None, choices=["json", "neo4j"]); ap.add_argument("--store-path", default=None)
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    frags = load_fragments(a.graph, [r["name"] for r in cfg["repos"]["repos"]], include_linked=True)
    if not frags:
        raise SystemExit(f"no fragments in {a.graph}; run the scanners and the linker first")
    g = Graph.from_fragments(frags)
    fresh = S.make_freshness(g, g.commits, "full")
    with S.open_store(cfg, a.store, a.store_path, root=pathlib.Path(".").resolve()) as st:
        print(json.dumps({"store": st.describe(), **st.write_full(g, fresh)}))


if __name__ == "__main__":
    main()
