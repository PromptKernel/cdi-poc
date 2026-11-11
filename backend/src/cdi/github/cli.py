"""`cdi github baseline|pr`: the entry points the composite action calls."""
from __future__ import annotations
import argparse, sys
from . import flow


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cdi github", description=__doc__)
    ap.add_argument("mode", choices=["baseline", "pr"])
    ap.add_argument("--root", default=".", help="repository checkout (the BASE revision for pr mode)")
    ap.add_argument("--config", default=None, help="path to .cdi/config.yml (read from the checkout, i.e. the base revision)")
    ap.add_argument("--store-path", default=None, help="baseline file (restored from / saved to the Actions cache by the workflow)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    fn = flow.run_baseline_flow if a.mode == "baseline" else flow.run_pr_flow
    return fn(a.root, a.config, a.store_path, a.out)


if __name__ == "__main__":
    sys.exit(main())
