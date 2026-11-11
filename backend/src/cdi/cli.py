"""`cdi` command line: one entry point for the whole tool. `cdi <command> --help` shows that command's options."""
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
    return runpy.run_path(str(tool), run_name="audit_hardcoding")["main"](argv)


def _config(argv):
    ap = argparse.ArgumentParser(prog="cdi config", description="Inspect the configuration (.cdi/config.yml merged with its profile and environment overrides).")
    ap.add_argument("what", choices=["show", "validate", "schema", "profiles"],
                    help="show: print the resolved configuration; validate: check it; schema: print the JSON Schema; profiles: list framework profiles")
    ap.add_argument("--file", default=None, help="path to .cdi/config.yml (default: $CDI_CONFIG or .cdi/config.yml)")
    a = ap.parse_args(argv)
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


def _module(path, fn="main"):
    def run(argv):
        import importlib
        return getattr(importlib.import_module(path), fn)(argv)
    return run


# name -> (handler(argv) -> exit code, one-line description). Each handler parses its own options: `cdi <name> --help`.
COMMANDS = {
    "baseline": (_module("cdi.pipeline.baseline"), "build the baseline graph (full | incremental) and write it to the store"),
    "pr": (_module("cdi.pipeline.run_pr"), "analyse a pull request locally against the baseline; writes the comment and status as files (advisory)"),
    "export": (_module("cdi.export"), "export the baseline and reports as a static snapshot for the explorer (out/explorer)"),
    "serve": (_module("cdi.api.serve"), "run the read-only HTTP API (127.0.0.1 by default; optional bearer token)"),
    "audit": (_audit, "fail if sample-specific names appear in backend/ or frontend/ source"),
    "config": (_config, "show, validate or print the schema of the configuration"),
    "github": (_module("cdi.github.cli"), "GitHub flow: `github baseline` (push to the base branch) and `github pr` (pull_request event)"),
}


def build_parser():
    lines = "\n".join(f"  {n:<9} {d}" for n, (_, d) in COMMANDS.items())
    return argparse.ArgumentParser(
        prog="cdi", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Cross-layer dependency graph and pull-request impact analysis.",
        epilog=f"commands:\n{lines}\n\nRun `cdi <command> --help` for the options of a command. Configuration lives in the target repository's .cdi/config.yml "
               f"(see docs/configuration.md); the baseline store is a JSON file by default (docs/graph-store.md).")


def main(argv=None):
    import signal
    try:                                     # a terminated run must still clean up the temporary scanner configuration (atexit runs on SystemExit)
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    except ValueError:                       # not the main thread (tests)
        pass
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help"):
        build_parser().print_help()
        return 0
    if argv[0] not in COMMANDS:
        print(f"cdi: unknown command {argv[0]!r}; choose from {', '.join(COMMANDS)}", file=sys.stderr)
        return 2
    try:
        code = COMMANDS[argv[0]][0](argv[1:])
    except SystemExit as e:                  # sub-commands exit via argparse/sys.exit; a string is an error message
        code = e.code
        if isinstance(code, str):
            print(code, file=sys.stderr)
            return 1
    return code if isinstance(code, int) else (0 if code is None else 1)


if __name__ == "__main__":
    sys.exit(main())
