"""Risk label selection from config/risk-rules.yml. First matching rule wins; no catch-all: no rule => no label."""
from __future__ import annotations
import fnmatch, pathlib
import yaml

BOOL_KEYS = {"in_critical_list", "has_consumers", "confirmed_path_reaches_ui", "inferred_path_reaches_ui", "reaches_api_endpoint",
             "introduces_unresolved", "has_own_unresolved"}
KEYS = BOOL_KEYS | {"change", "kind_in", "min_consumers"}


def load(path):
    cfg = yaml.safe_load(pathlib.Path(path).read_text())
    validate(cfg)
    return cfg


def validate(cfg):
    labels = cfg.get("labels") or []
    for r in cfg.get("rules", []):
        if r.get("label") not in labels:
            raise ValueError(f"rule {r.get('id')}: label {r.get('label')!r} not in labels {labels}")
        bad = set(r.get("when", {})) - KEYS
        if bad:
            raise ValueError(f"rule {r.get('id')}: unknown condition keys {sorted(bad)}")
        if not r.get("when"):
            raise ValueError(f"rule {r.get('id')}: empty `when` would match everything; no catch-all rules are allowed")
        if not r.get("explain") or not r.get("action"):
            raise ValueError(f"rule {r.get('id')}: needs `explain` and `action`")


def in_critical_list(cfg, name):
    return any(fnmatch.fnmatchcase(name, pat) for pat in cfg.get("critical_objects", []))


def _holds(key, want, facts):
    if key == "change":
        return facts["change"] in (want if isinstance(want, list) else [want])
    if key == "kind_in":
        return facts["kind"] in want
    if key == "min_consumers":
        return facts["consumer_count"] >= want
    return bool(facts[key]) is bool(want)


def select(cfg, facts):
    """Return the first rule whose conditions all hold, or None."""
    for r in cfg.get("rules", []):
        if all(_holds(k, v, facts) for k, v in r["when"].items()):
            return r
    return None


def describe_match(rule, facts):
    return "; ".join(f"{k} = {facts[k] if k in facts else '?'}" if k not in ("kind_in", "min_consumers") else f"{k} {rule['when'][k]}" for k in rule["when"])
