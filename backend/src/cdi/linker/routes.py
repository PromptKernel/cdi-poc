"""Route matching between frontend request templates and API route templates. Pure functions, driven by config (routes.yml: matching)."""
from __future__ import annotations
import re

DEFAULTS = {"param_token": "{}", "case_sensitive": False, "strip_leading_slash": True}


def segments(template: str, cfg: dict | None = None):
    """Split a URL/route template into segments; each is ('lit', text) or ('param', None)."""
    c = {**DEFAULTS, **(cfg or {})}
    t = template.split("?", 1)[0].strip()
    if c["strip_leading_slash"]:
        t = t.lstrip("/")
    t = t.rstrip("/")
    if not c["case_sensitive"]:
        t = t.lower()
    out = []
    for seg in (t.split("/") if t else []):
        out.append(("param", None) if re.fullmatch(r"\{[^}]*\}", seg) else ("lit", seg))
    return out


def match(request_tpl: str, endpoint_tpl: str, cfg: dict | None = None):
    """Return 'exact', 'partial' or None.
    exact   - same number of segments; every literal equals; endpoint parameters accept anything.
    partial - as exact, but the request has a runtime placeholder where the endpoint has a literal (could be that endpoint, not certain)."""
    r, e = segments(request_tpl, cfg), segments(endpoint_tpl, cfg)
    if len(r) != len(e) or not r:
        return None
    partial = False
    for (rk, rv), (ek, ev) in zip(r, e):
        if ek == "param":
            continue
        if rk == "lit":
            if rv != ev:
                return None
        else:
            partial = True
    return "partial" if partial else "exact"


def verb_ok(request_verb: str, endpoint_verb: str) -> bool:
    return endpoint_verb in (None, "", "ANY") or request_verb == endpoint_verb
