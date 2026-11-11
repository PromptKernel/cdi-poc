"""`cdi` command line. Subcommands are added as the tool grows; today: audit, config (show / validate / schema / profiles), github (baseline | pr)."""
from __future__ import annotations
import argparse, json, runpy, sys
import yaml
from cdi import config as C
from cdi.paths import BACKEND_ROOT


def _audit(argv):
    """Delegates to backend/tools/audit_hardcoding.py (kept outside the package: it audits the source tree, not an installed tool)."""
    tool = BACKEND_ROOT / "tools" / "audit_hardcoding.py"
    if not tool.is_file():
        print(f"cdi audit needs a source checkout: {tool} not found", file=sys.stderr)
        return 2
    mod = runpy.run_path(str(tool), run_name="audit_hardcoding")
    return mod["main"](argv)


def _config(a):
    if a.what == "schema":
        print(json.dumps(C.schema(), indent=2)); return 0
    if a.what == "profiles":
        print("\n".join(C.profiles())); return 0
    try:
        cfg = C.load(a.file)
    except C.ConfigError as e:
        print(f"config error: {e}", file=sys.stderr); return 2
    if a.what == "validate":
        print(f"ok: {cfg['_file']} ({len(cfg['repos'])} repos, profile {cfg.get('profile') or '-'})"); return 0
    print(yaml.safe_dump({k: v for k, v in cfg.items() if not k.startswith("_")}, sort_keys=False)); return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "github":
        from cdi.github import cli as gh
        return gh.main(argv[1:])
    if argv and argv[0] == "audit":          # options belong to the audit tool; see backend/tools/audit_hardcoding.py --help
        return _audit(argv[1:])
    ap = argparse.ArgumentParser(prog="cdi", description="Cross-layer dependency graph and PR impact analysis")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit", help="fail if sample-specific identifiers appear in backend/ or frontend/ source (options: --root, --json)")
    sub.add_parser("github", help="GitHub flow: `cdi github baseline|pr` (used by the composite action)")
    cf = sub.add_parser("config", help="inspect the configuration")
    cf.add_argument("what", choices=["show", "validate", "schema", "profiles"])
    cf.add_argument("--file", default=None, help="path to .cdi/config.yml (default: $CDI_CONFIG or .cdi/config.yml)")
    a = ap.parse_args(argv)
    return _config(a)


if __name__ == "__main__":
    sys.exit(main())
