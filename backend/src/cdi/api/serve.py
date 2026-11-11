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
    ap.add_argument("--host", default=os.environ.get("CDI_API_HOST", "127.0.0.1"), help="listen address (default: $CDI_API_HOST or 127.0.0.1; anything else needs a token)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("CDI_API_PORT", "8000")), help="port (default: $CDI_API_PORT or 8000)")
    ap.add_argument("--token-env", default="CDI_API_TOKEN", help="NAME of the environment variable holding the bearer token (unset = no auth, localhost only)")
    ap.add_argument("--cors-origin", action="append", default=None,
                    help="origin allowed to call the API from a browser (repeatable), e.g. http://127.0.0.1:5173; default: the comma separated $CDI_CORS_ORIGINS. "
                         "Never '*': a wildcard is refused")
    return ap


def cors_origins(a, environ=None):
    """Explicit origins only. A wildcard (or the opaque 'null' origin) is refused: the API may hold a token and must not be callable from any page."""
    env = os.environ if environ is None else environ
    origins = a.cors_origin if a.cors_origin is not None else [o.strip() for o in env.get("CDI_CORS_ORIGINS", "").split(",") if o.strip()]
    for o in origins:
        if "*" in o or o.lower() == "null" or not o.startswith(("http://", "https://")):
            raise SystemExit(f"refusing CORS origin {o!r}: list explicit http(s) origins such as http://127.0.0.1:5173 (no wildcards)")
    return origins


def make_app(a, environ=None):
    from cdi.api import create_app
    env = os.environ if environ is None else environ
    cfg = load_config(a.config, env)
    root = pathlib.Path(cfg["root"])
    return create_app(cfg, lambda: S.open_store(cfg, a.store, a.store_path, root=root), reports_dir=a.reports_dir, token_env=a.token_env,
                      cors_origins=cors_origins(a, env), environ=env)


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
