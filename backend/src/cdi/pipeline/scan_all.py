"""Run the scanner plugin selected for every logical repo in .cdi/config.yml, then validate the fragments against the graph schema.
Run from the target repository root. Scanners refuse to run when a logical repo's folder has uncommitted changes."""
from __future__ import annotations
import argparse, pathlib, shutil, sys
from cdi import config as C
from cdi.paths import BACKEND_ROOT
from cdi.pipeline.scanrun import ScanRunner
from cdi import validate


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None); ap.add_argument("--out", default="out/graph")
    a = ap.parse_args(argv)
    cfg = C.load(a.config)
    view = C.scanner_view(cfg, absolute_paths=True)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    runner = ScanRunner(BACKEND_ROOT, C.materialize(cfg), out / ".work")
    files = []
    for r in view["repos"]["repos"]:
        frag = runner.scan(r, r["path"])
        dst = out / f"{r['name']}.json"
        shutil.copyfile(runner.work / f"scan_{r['name']}.json", dst)
        print(f"[scan] {r['name']} ({r['plugin']}): nodes={len(frag['nodes'])} edges={len(frag['edges'])} -> {dst}")
        files.append(str(dst))
    sys.exit(validate.main(files) or 0)


if __name__ == "__main__":
    main()
