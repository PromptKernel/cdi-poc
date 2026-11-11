"""Configuration for a target repository: `.cdi/config.yml`.

Precedence (low to high): tool defaults (profiles/_base.yml) < framework profile (`profile:` key) < the repo's config file < environment
overrides (`CDI__section__key=<yaml value>`). The merged result is validated against backend/schema/config.schema.json.
Secrets never live in the config; the file only names the environment variable that holds them."""
from __future__ import annotations
import copy, hashlib, json, os, pathlib, tempfile
import jsonschema, yaml
from cdi import plugins
from cdi.paths import SCHEMA_DIR

PROFILE_DIR = pathlib.Path(__file__).resolve().parent / "profiles"
DEFAULT_CONFIG = ".cdi/config.yml"
ENV_PREFIX = "CDI__"


class ConfigError(ValueError):
    pass


def deep_merge(a, b):
    """b over a: dicts merge recursively, everything else (lists included) is replaced."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = deep_merge(a[k], v) if k in a else copy.deepcopy(v)
        return out
    return copy.deepcopy(b)


def profiles() -> list[str]:
    return sorted(p.stem for p in PROFILE_DIR.glob("*.yml") if not p.stem.startswith("_"))


def _load_profile(name):
    f = PROFILE_DIR / f"{name}.yml"
    if name.startswith("_") or not f.is_file():
        raise ConfigError(f"unknown profile {name!r}; available: {profiles()}")
    return yaml.safe_load(f.read_text())


def env_overrides(environ=None) -> dict:
    """CDI__ci__blocking__enabled=true  ->  {"ci": {"blocking": {"enabled": True}}}. Values are parsed as YAML."""
    out: dict = {}
    for k, v in (os.environ if environ is None else environ).items():
        if not k.startswith(ENV_PREFIX):
            continue
        path = [p for p in k[len(ENV_PREFIX):].split("__") if p]
        if not path:
            continue
        cur = out
        for p in path[:-1]:
            cur = cur.setdefault(p, {})
            if not isinstance(cur, dict):
                raise ConfigError(f"environment override {k} conflicts with another override")
        cur[path[-1]] = yaml.safe_load(v)
    return out


def schema() -> dict:
    return json.loads((SCHEMA_DIR / "config.schema.json").read_text())


def validate(cfg: dict):
    errs = sorted(jsonschema.Draft202012Validator(schema()).iter_errors(cfg), key=lambda e: list(e.absolute_path))
    if errs:
        lines = [f"  {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errs[:15]]
        raise ConfigError("invalid configuration:\n" + "\n".join(lines))
    names = [r["name"] for r in cfg["repos"]]
    if len(set(names)) != len(names):
        raise ConfigError("invalid configuration: repo names must be unique")
    for r in cfg["repos"]:
        try:
            plugins.get(r["scanner"]["plugin"])
        except KeyError as e:
            raise ConfigError(f"repos/{r['name']}/scanner/plugin: {e.args[0]}") from None
    labels = cfg["risk"]["labels"]
    for r in cfg["risk"]["rules"]:
        if r["label"] not in labels:
            raise ConfigError(f"risk rule {r['id']}: label {r['label']!r} not in labels {labels}")


def config_path(path=None, environ=None) -> pathlib.Path:
    env = os.environ if environ is None else environ
    p = pathlib.Path(path or env.get("CDI_CONFIG") or DEFAULT_CONFIG)
    if p.is_dir():
        p = p / "config.yml" if (p / "config.yml").is_file() else p / DEFAULT_CONFIG
    return p


def repo_root_of(cfg_file: pathlib.Path) -> pathlib.Path:
    """Repository root = the parent of the `.cdi` folder that holds the config file (or the file's folder otherwise)."""
    d = cfg_file.resolve().parent
    return d.parent if d.name == ".cdi" else d


def resolve(raw: dict, environ=None) -> dict:
    """Apply defaults, profile and env overrides to a raw config dict; validate; fill in scanner globs from the plugin."""
    cfg = deep_merge(yaml.safe_load((PROFILE_DIR / "_base.yml").read_text()), {})
    if raw.get("profile"):
        cfg = deep_merge(cfg, _load_profile(raw["profile"]))
    cfg = deep_merge(cfg, raw)
    cfg = deep_merge(cfg, env_overrides(environ))
    validate(cfg)
    for r in cfg["repos"]:
        pl = plugins.get(r["scanner"]["plugin"])
        r["scanner"].setdefault("include", list(pl.default_include))
        r["scanner"].setdefault("exclude", list(pl.default_exclude))
        r.setdefault("main_branch", cfg["branches"]["base"])
    return cfg


def load(path=None, environ=None) -> dict:
    """Load, merge and validate. Returns the resolved config with `_root` (repository root) and `_file` added."""
    f = config_path(path, environ)
    if not f.is_file():
        raise ConfigError(f"config file not found: {f} (create one from config.example/ or pass --config)")
    try:
        raw = yaml.safe_load(f.read_text()) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{f}: not valid YAML: {e}") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{f}: top level must be a mapping")
    cfg = resolve(raw, environ)
    cfg["_root"], cfg["_file"] = str(repo_root_of(f)), str(f.resolve())
    return cfg


# ---- the view the scanners and the rest of the tool consume --------------------------------------------------------------------------------

def scanner_view(cfg: dict, absolute_paths=False) -> dict:
    """Files in the shape the scanners read (repos / routes / naming), derived from the resolved config."""
    root, c = pathlib.Path(cfg["_root"]), cfg["conventions"]
    repos = []
    for r in cfg["repos"]:
        pl = plugins.get(r["scanner"]["plugin"])
        p = pathlib.Path(r["path"])
        repos.append({"name": r["name"], "path": str(p if p.is_absolute() or not absolute_paths else root / p), "kind": pl.layer, "plugin": pl.id,
                      "main_branch": r["main_branch"], "include": r["scanner"]["include"], "exclude": r["scanner"]["exclude"]})
    return {
        "repos": {"repos": repos, "synthetic": cfg["synthetic"]},
        "routes": {"api": c["api"], "frontend": {k: v for k, v in c["frontend"].items()}, "matching": c["matching"]},
        "naming": {"layers": c["layers"], "sql": c["sql"], "sql_access": c["sql_access"], "tests": c["tests"]},
    }


def materialize(cfg: dict) -> pathlib.Path:
    """Write the scanner view to a content-addressed folder under the system temp dir (idempotent; nothing is deleted) and return it."""
    view = scanner_view(cfg, absolute_paths=True)
    blob = json.dumps(view, sort_keys=True)
    d = pathlib.Path(tempfile.gettempdir()) / f"cdi-scanner-config-{hashlib.sha256(blob.encode()).hexdigest()[:16]}"
    d.mkdir(exist_ok=True)
    for name in ("repos", "routes", "naming"):
        f = d / f"{name}.yml"
        text = yaml.safe_dump(view[name], sort_keys=False)
        if not f.exists() or f.read_text() != text:
            f.write_text(text)
    return d


def as_legacy(cfg: dict) -> dict:
    """The dict the linker, impact engine, store and CI code read: repos / routes / naming / graph / risk-rules / ci."""
    v = scanner_view(cfg)
    lim = cfg["limits"]
    ci = copy.deepcopy(cfg["ci"])
    ci["comment"]["max_chars"] = lim["comment_max_chars"]
    graph = {**{k: copy.deepcopy(cfg["graph"][k]) for k in ("neo4j", "load", "trace")},
             "impact": {**copy.deepcopy(cfg["impact"]), "max_depth_downstream": lim["max_depth_downstream"], "max_depth_upstream": lim["max_depth_upstream"]}}
    return {**v, "graph": graph, "risk-rules": copy.deepcopy(cfg["risk"]), "ci": ci, "limits": copy.deepcopy(lim), "branches": copy.deepcopy(cfg["branches"]),
            "store": cfg["graph"]["store"], "dir": str(materialize(cfg)), "root": cfg["_root"], "file": cfg["_file"]}
