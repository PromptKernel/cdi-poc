"""PR impact analysis.
usage: python -m cdi.impact.cli --pr <branch> [--target <branch>] [--name pr-a] [--store json|neo4j] [--store-path FILE] [--out out]
--target defaults to branches.base of .cdi/config.yml. Reads the baseline graph read-only from the configured store, never writes to it. Output: out/report-<name>.md and .json."""
from __future__ import annotations
import argparse, pathlib, sys
from cdi.linker.graphio import load_config
from . import engine, report

from cdi.paths import BACKEND_ROOT as TOOL_ROOT


def load_baseline(cfg, source=None, path=None):
    """Read the baseline from the configured store (json | neo4j; `source` overrides). Raises cdi.store.BaselineMissing / BaselineSchemaMismatch."""
    from cdi import store
    with store.open_store(cfg, source, path) as st:
        return st.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=None, help="branch to compare with (default: branches.base from the config)"); ap.add_argument("--pr", required=True); ap.add_argument("--name")
    ap.add_argument("--store", default=None, choices=["json", "neo4j"], help="baseline store (default: graph.store from the config)"); ap.add_argument("--store-path", default=None, help="JSON baseline file")
    ap.add_argument("--config", default=None, help="path to .cdi/config.yml (default: $CDI_CONFIG or .cdi/config.yml)"); ap.add_argument("--out", default="out")
    a = ap.parse_args(argv)
    root = pathlib.Path(".").resolve()
    cfg = load_config(a.config)
    target = a.target or cfg["branches"]["base"]
    try:
        base, fresh = load_baseline(cfg, a.store, a.store_path)
    except Exception as e:
        sys.exit(f"[impact] {e}")
    base.commits = dict(fresh["commits"])
    res = engine.analyze(root, TOOL_ROOT, a.config, target, a.pr, base, fresh, name=a.name or a.pr)
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    slug = (a.name or a.pr).replace("/", "_")
    (out / f"report-{slug}.md").write_text(report.render(res))
    (out / f"report-{slug}.json").write_text(report.to_json(res))
    print(f"[impact] {out / f'report-{slug}.md'}  objects={len(res['objects'])}  PR run {res['meta']['timing_s']['total_pr_run']} s")
    for w in res["meta"]["warnings"]:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
