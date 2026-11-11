"""`cdi serve`: run the read-only API with uvicorn.
Binds to 127.0.0.1 by default. A non-loopback host is refused unless a bearer token is configured (environment variable named by --token-env)."""
from __future__ import annotations
import argparse, ipaddress, os, pathlib, sys
from cdi import store as S
from cdi.linker.graphio import load_config

LOOPBACK = ("127.0.0.1", "::1", "localhost")


def is_loopback(host: str) -> bool:
    if host in LOOPBACK:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_bind(host: str, token_set: bool):
    """Raises SystemExit with the reason when this host must not be used without authentication."""
    if not is_loopback(host) and not token_set:
        raise SystemExit(f"refusing to listen on {host!r} without authentication: set a token in the environment variable named by --token-env "
                         f"(clients then send 'Authorization: Bearer <token>'), or bind to 127.0.0.1")


def build_parser():
    ap = argparse.ArgumentParser(prog="cdi serve", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="path to .cdi/config.yml (default: $CDI_CONFIG or .cdi/config.yml)")
    ap.add_argument("--store", default=None, choices=["json", "neo4j"], help="baseline store (default: graph.store from the config)")
    ap.add_argument("--store-path", default=None, help="JSON baseline file (default: graph.json.path)")
    ap.add_argument("--reports-dir", default="out", help="folder holding report-*.md/.json and pr-comment.md (default: out)")
    ap.add_argument("--host", default="127.0.0.1", help="listen address (default 127.0.0.1; anything else needs a token)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--token-env", default="CDI_API_TOKEN", help="NAME of the environment variable holding the bearer token (unset = no auth, localhost only)")
    ap.add_argument("--cors-origin", action="append", default=[], help="origin allowed to call the API from a browser (repeatable), e.g. http://127.0.0.1:5173")
    return ap


def make_app(a, environ=None):
    from cdi.api import create_app
    env = os.environ if environ is None else environ
    cfg = load_config(a.config, env)
    root = pathlib.Path(cfg["root"])
    return create_app(cfg, lambda: S.open_store(cfg, a.store, a.store_path, root=root), reports_dir=a.reports_dir, token_env=a.token_env,
                      cors_origins=a.cors_origin, environ=env)


def main(argv=None):
    a = build_parser().parse_args(argv)
    check_bind(a.host, bool(os.environ.get(a.token_env)))
    app = make_app(a)
    import uvicorn
    print(f"[serve] http://{a.host}:{a.port}  (OpenAPI: /openapi.json, docs: /docs)  auth: {'bearer token' if os.environ.get(a.token_env) else 'none (localhost only)'}", file=sys.stderr)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
