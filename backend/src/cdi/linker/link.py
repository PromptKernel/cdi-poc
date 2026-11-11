"""Cross-repo linker: adds ROUTES_TO, RESOLVES_TO and TESTS edges to the scanner fragments.

Everything it needs comes from config/ (routes.yml `matching`, naming.yml `sql` and `tests`), nothing is specific to the sample.
It never promotes confidence: exact unique matches are CONFIRMED_STATIC, heuristic or ambiguous matches are INFERRED,
and anything that cannot be matched becomes an UNRESOLVED edge to an UNRESOLVED placeholder node with a reason.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, re, sys
from . import routes
from .graphio import Graph, load_config, load_fragments

SQL_KINDS = {"procedure": ("SQL_PROC",), "table_or_view": ("SQL_TABLE", "SQL_VIEW"), "table": ("SQL_TABLE",), "view": ("SQL_VIEW",)}
TARGETABLE = {"UI_COMPONENT", "UI_SERVICE_METHOD", "API_ENDPOINT", "SERVICE_METHOD", "DATA_ACCESS_METHOD", "METHOD",
              "INTERFACE_METHOD", "SQL_PROC", "SQL_VIEW", "SQL_TABLE"}


class Linker:
    def __init__(self, graph: Graph, cfg: dict):
        self.g, self.cfg = graph, cfg
        self.nodes_out: dict[str, dict] = {}
        self.edges_out: list[dict] = []
        self.match_cfg = (cfg["routes"] or {}).get("matching", {})
        self.default_schema = ((cfg["naming"] or {}).get("sql") or {}).get("default_schema", "dbo")

    # ---------- helpers ----------
    def _unresolved_node(self, cause, key, label):
        nid = f"linker:unresolved:{cause}:{key}"
        self.nodes_out.setdefault(nid, {"id": nid, "kind": "UNRESOLVED", "name": label, "repo": "linker", "synthetic": False,
                                        "attrs": {"cause": cause}})
        return nid

    def _site_from_edge(self, e):
        return {"repo": e["repo"], "file": e["source_file"], "location": e["location"], "evidence": e.get("evidence", ""),
                "synthetic": e["synthetic"]}

    def _site_from_node(self, n):
        loc = n.get("location") or {"line": 1}
        return {"repo": n["repo"], "file": n.get("file", ""), "location": {"line": loc["line"], "end_line": loc.get("end_line", loc["line"])},
                "evidence": "", "synthetic": n.get("synthetic", False)}

    def _edge(self, typ, src, tgt, site, method, conf, reason=None, attrs=None):
        loc = site["location"]
        e = {"id": f"{typ}|{src}|{tgt}|{site['file']}:{loc['line']}:{loc.get('column', 0)}", "type": typ, "source": src, "target": tgt,
             "source_file": site["file"], "location": loc, "analysis_method": method, "confidence": conf,
             "commit_id": self.g.commits[site["repo"]], "repo": site["repo"], "synthetic": site["synthetic"]}
        if site.get("evidence"):
            e["evidence"] = site["evidence"]
        if reason:
            e["reason"] = reason
        if attrs:
            e["attrs"] = attrs
        assert conf == "CONFIRMED_STATIC" or reason, "INFERRED/UNRESOLVED edges need a reason"
        self.edges_out.append(e)
        return e

    @staticmethod
    def _loc(n):
        l = n.get("location") or {}
        return f"{n.get('file', '?')}:{l.get('line', '?')}"

    # ---------- 1. HTTP request -> API endpoint ----------
    def link_routes(self):
        endpoints = [n for n in self.g.nodes.values() if n["kind"] == "API_ENDPOINT" and (n.get("attrs") or {}).get("route_template")]
        sites = collections.defaultdict(list)
        for e in self.g.edges.values():
            if e["type"] == "MAKES_REQUEST":
                sites[e["target"]].append(e)
        for n in sorted((n for n in self.g.nodes.values() if n["kind"] == "HTTP_REQUEST"), key=lambda n: n["id"]):
            a = n["attrs"]
            site = self._site_from_edge(sorted(sites[n["id"]], key=lambda e: (e["source_file"], e["location"]["line"]))[0]) \
                if sites[n["id"]] else self._site_from_node(n)
            cands = []
            for ep in endpoints:
                if not routes.verb_ok(a["verb"], ep["attrs"].get("http_method")):
                    continue
                m = routes.match(a["url_template"], ep["attrs"]["route_template"], self.match_cfg)
                if m:
                    cands.append((m, ep))
            exact = [ep for m, ep in cands if m == "exact"]
            partial = [ep for m, ep in cands if m == "partial"]
            pick, kind = (exact, "exact") if exact else (partial, "partial")
            if not pick:
                tgt = self._unresolved_node("no_matching_route", n["name"], f"no API endpoint matches {n['name']}")
                self._edge("ROUTES_TO", n["id"], tgt, site, "linker:route-match", "UNRESOLVED",
                           f"no API endpoint with verb {a['verb']} and a route matching '{a['url_template']}' in the scanned repos")
                continue
            for ep in sorted(pick, key=lambda x: x["id"]):
                attrs = {"target_location": self._loc(ep), "route_template": ep["attrs"]["route_template"], "request_template": a["url_template"]}
                if kind == "exact" and len(pick) == 1:
                    self._edge("ROUTES_TO", n["id"], ep["id"], site, "linker:route-match", "CONFIRMED_STATIC", None, attrs)
                elif kind == "exact":
                    self._edge("ROUTES_TO", n["id"], ep["id"], site, "linker:route-match", "INFERRED",
                               f"ambiguous: {len(pick)} endpoints match this request exactly", attrs)
                else:
                    self._edge("ROUTES_TO", n["id"], ep["id"], site, "linker:route-match", "INFERRED",
                               "request has a runtime-valued segment where the endpoint route has a literal", attrs)

    # ---------- 2. SQL reference -> definition ----------
    def link_sql(self):
        defs = collections.defaultdict(list)
        for n in self.g.nodes.values():
            if n["kind"] in ("SQL_PROC", "SQL_TABLE", "SQL_VIEW"):
                defs[n["name"].lower()].append(n)
        refsites = collections.defaultdict(list)
        for e in self.g.edges.values():
            if self.g.nodes.get(e["target"], {}).get("kind") == "SQL_REF":
                refsites[e["target"]].append(e)
        for ref in sorted((n for n in self.g.nodes.values() if n["kind"] == "SQL_REF"), key=lambda n: n["id"]):
            sites = sorted(refsites[ref["id"]], key=lambda e: (e["repo"], e["source_file"], e["location"]["line"]))
            if not sites:
                continue
            site = self._site_from_edge(sites[0])
            expected = (ref.get("attrs") or {}).get("expected", "procedure")
            ok = [d for d in defs.get(ref["name"].lower(), []) if d["kind"] in SQL_KINDS.get(expected, SQL_KINDS["procedure"])]
            ref_attrs = {"referenced_from": [f"{e['repo']}:{e['source_file']}:{e['location']['line']}" for e in sites]}
            if len(ok) == 1:
                self._edge("RESOLVES_TO", ref["id"], ok[0]["id"], site, "linker:sql-name-match", "CONFIRMED_STATIC", None,
                           {**ref_attrs, "target_location": self._loc(ok[0])})
            elif len(ok) > 1:
                for d in ok:
                    self._edge("RESOLVES_TO", ref["id"], d["id"], site, "linker:sql-name-match", "INFERRED",
                               f"ambiguous: {len(ok)} definitions named {ref['name']}", {**ref_attrs, "target_location": self._loc(d)})
            else:
                tgt = self._unresolved_node("referenced_not_found", ref["name"], f"referenced {expected} {ref['name']} not found")
                self._edge("RESOLVES_TO", ref["id"], tgt, site, "linker:sql-name-match", "UNRESOLVED",
                           f"referenced {expected} '{ref['name']}' is called/used but no definition was found in any scanned repo", ref_attrs)

    # ---------- 3. test -> covered node ----------
    def link_tests(self):
        tcfg = (self.cfg["naming"] or {}).get("tests", {})
        pat = re.compile((tcfg.get("csharp") or {}).get("method_pattern", r"$^"))
        for t in sorted((n for n in self.g.nodes.values() if n["kind"] == "TEST"), key=lambda n: n["id"]):
            site = self._site_from_node(t)
            a = t.get("attrs") or {}
            annotated: dict[str, dict] = {}
            for text in a.get("covers_annotation", []):
                hits = [n for n in self.g.nodes.values() if n["name"] == text and n["kind"] in TARGETABLE]
                if not hits:
                    tgt = self._unresolved_node("annotation_target_not_found", text, f"annotation target {text} not found")
                    self._edge("TESTS", t["id"], tgt, site, "annotation", "UNRESOLVED",
                               f"@covers target '{text}' matches no scanned node", {"mapping_method": "annotation"})
                for h in hits:
                    annotated[h["id"]] = h
                    if len(hits) == 1:
                        self._edge("TESTS", t["id"], h["id"], site, "annotation", "CONFIRMED_STATIC", None, {"mapping_method": "annotation"})
                    else:
                        self._edge("TESTS", t["id"], h["id"], site, "annotation", "INFERRED",
                                   f"ambiguous annotation: {len(hits)} nodes are named '{text}'", {"mapping_method": "annotation"})
            conv: list[dict] = []
            m = pat.match(a.get("method_name", "")) if a.get("test_layer") == "csharp" else None
            if m:
                rx = re.compile(r"\.%s\.%s\(" % (re.escape(m["target"]), re.escape(m["member"])))
                conv += [n for n in self.g.nodes.values() if n["repo"] == t["repo"] and n["kind"] in TARGETABLE and rx.search(n["name"])]
            cf = a.get("convention_target_file")
            if cf:
                conv += [n for n in self.g.nodes.values() if n["repo"] == t["repo"] and n.get("file") == cf
                         and n["kind"] in ("UI_COMPONENT", "UI_SERVICE_METHOD")]
            for n in sorted(conv, key=lambda n: n["id"]):
                if n["id"] in annotated:
                    continue   # already covered by an explicit annotation; keep the stronger mapping only
                self._edge("TESTS", t["id"], n["id"], site, "naming-convention", "INFERRED",
                           "mapped by naming convention (not by symbol reference or annotation)", {"mapping_method": "naming-convention"})

    def run(self):
        self.link_routes(); self.link_sql(); self.link_tests()
        return self


def build_fragment(linker: Linker):
    inputs = dict(sorted(linker.g.commits.items()))
    composite = hashlib.sha1("\n".join(f"{k}={v}" for k, v in inputs.items()).encode()).hexdigest()
    return {"schema_version": "1.0", "repo": "linked", "commit_id": composite, "inputs": inputs,
            "scanner": {"name": "linker", "version": "1.0"},
            "nodes": sorted(linker.nodes_out.values(), key=lambda n: n["id"]),
            "edges": sorted(linker.edges_out, key=lambda e: e["id"])}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Link scanner fragments across repos")
    ap.add_argument("--config", default="config")
    ap.add_argument("--graph", default="out/graph")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    frags = load_fragments(a.graph, [r["name"] for r in cfg["repos"]["repos"]])
    if not frags:
        sys.exit("no scanner fragments found; run pipeline/scan_all.sh first")
    lk = Linker(Graph.from_fragments(frags), cfg).run()
    frag = build_fragment(lk)
    out = pathlib.Path(a.out or pathlib.Path(a.graph) / "linked.json")
    out.write_text(json.dumps(frag, indent=2))
    c = collections.Counter((e["type"], e["confidence"]) for e in frag["edges"])
    print(f"[linker] inputs={frag['inputs']}")
    for (t, conf), n in sorted(c.items()):
        print(f"  {t:<10} {conf:<17} {n}")
    print(f"[linker] {len(frag['nodes'])} placeholder nodes, {len(frag['edges'])} edges -> {out}")


if __name__ == "__main__":
    main()
