"""Impact engine: PR diff -> changed objects -> consumers / dependencies / tests -> risk. Read-only with respect to the baseline graph."""
from __future__ import annotations
import collections, pathlib, time
from cdi.linker import merge as M
from cdi.linker.graphio import Graph, RANK, load_config
from cdi.pipeline.baseline import checkout, repo_entries
from cdi.pipeline.scanrun import ScanRunner
from . import diff as D, mapper, risk
from . import traverse as T

CONF_ORDER = ["CONFIRMED_STATIC", "INFERRED", "UNRESOLVED"]
EXCL = ("USES_TYPE",)   # type references are not dependency paths worth reporting
TEST_RANK = {"annotation": 0, "static-reference": 1, "convention": 2}   # explicit annotation > static reference > naming/file convention


def test_sort_key(t):
    return (TEST_RANK[t["mapping"]], CONF_ORDER.index(t["confidence"]), len(t["path"]), t["name"])


def edge_key(e):
    return (e["type"], e["source"], e["target"])


def short(c):
    return (c or "")[:8]


def cite(g: Graph, edge_id):
    e = g.edges[edge_id]
    return {"edge_id": edge_id, "type": e["type"], "confidence": e["confidence"], "repo": e["repo"], "file": e["source_file"], "line": e["location"]["line"],
            "method": e["analysis_method"], "commit": e["commit_id"], "synthetic": e["synthetic"], "reason": e.get("reason"),
            "evidence": e.get("evidence", ""), "source": g.nodes.get(e["source"], {}).get("name", e["source"]),
            "target": g.nodes.get(e["target"], {}).get("name", e["target"]), "attrs": e.get("attrs") or {},
            "source_kind": g.nodes.get(e["source"], {}).get("kind", "?"), "target_kind": g.nodes.get(e["target"], {}).get("kind", "?"),
            "target_id": e["target"], "target_cause": (g.nodes.get(e["target"], {}).get("attrs") or {}).get("cause")}


def path_view(g, path, head_keys=None, head=None):
    out = []
    for h in path:
        c = cite(g, h["edge_id"])
        c["from"], c["to"] = h["from_name"], h["to_name"]
        if head_keys is not None and edge_key(g.edges[h["edge_id"]]) not in head_keys:
            c["broken_by_pr"] = True
            rep = replacement(g.edges[h["edge_id"]], head)
            if rep:
                c["replacement"] = rep
        out.append(c)
    return out


def replacement(e, head: Graph):
    """What the head graph has instead of a baseline edge that disappeared: an edge of the same type from the same source with another target."""
    for x in head.out.get(e["source"], []):
        if x["type"] == e["type"] and x["target"] != e["target"]:
            return cite(head, x["id"])
    return None


def path_conf(path):
    return T.path_confidence(path)


def moved_files_that_matter(root, repos, merge_base, target_tip):
    """Files that changed on the target between the merge-base and its tip AND matter to the analysis: files a scanner reads (the repo's include/exclude
    globs) or the tool configuration (.cdi/). Anything else (a README, a workflow file) does not make the baseline unreliable for this PR."""
    if merge_base == target_tip:
        return []
    changed = D.git(root, "diff", "--name-only", "--no-renames", merge_base, target_tip).splitlines()
    out = []
    for f in changed:
        if f.startswith(".cdi/"):
            out.append(f); continue
        for r in repos:
            folder = r["path"].rstrip("/") + "/"
            if f.startswith(folder) and D.is_scanned(f[len(folder):], r.get("include", []), r.get("exclude", [])):
                out.append(f); break
    return out


def freshness_warnings(recorded, target_commits, merge_base, target_tip, moved=None):
    """`moved`: files from moved_files_that_matter(). None = unknown (warn whenever the merge-base is not the tip, the old behaviour)."""
    w = []
    if not recorded:
        w.append("No baseline freshness record found: cannot tell which commits the graph was built from.")
        return w
    for repo, cur in sorted(target_commits.items()):
        rec = (recorded.get("commits") or {}).get(repo)
        if rec != cur:
            w.append(f"Baseline is STALE for '{repo}': the graph was built from {short(rec)} but the target branch is at {short(cur)}. "
                     f"Results may miss changes already merged into the target.")
    if merge_base != target_tip and (moved is None or moved):
        what = "" if not moved else (f" {len(moved)} file(s) the scanners read or the configuration changed on the target since then "
                                     f"(for example `{moved[0]}`).")
        w.append(f"The PR branch is based on an OLDER target: merge-base is {short(merge_base)}, the target tip is {short(target_tip)}.{what} "
                 f"The diff covers only the PR's own changes (three-dot); changes merged into the target since the merge-base are not part of this analysis.")
    return w


def test_categories(g: Graph, test_id, affected):
    """All ways a test is tied to the affected node set: explicit annotation, static reference (a resolved edge from the test), or convention."""
    cats = set()
    for e in g.out.get(test_id, []):
        if e["target"] not in affected or e["confidence"] == "UNRESOLVED":
            continue
        if e["type"] == "TESTS":
            cats.add("annotation" if (e.get("attrs") or {}).get("mapping_method") == "annotation" else "convention")
        else:
            cats.add("static-reference")
    return cats


def classify(kind, groups):
    for g, kinds in groups.items():
        if kind in kinds:
            return g
    return None


def graph_delta(base: Graph, head: Graph):
    bn, hn = set(base.nodes), set(head.nodes)
    be, he = base.edges, head.edges
    added_e, removed_e = sorted(set(he) - set(be)), sorted(set(be) - set(he))
    kb = collections.defaultdict(list); kh = collections.defaultdict(list)
    skey = lambda e: (e["type"], e["source"], e["target"], e["source_file"])
    for i in removed_e: kb[skey(be[i])].append(i)
    for i in added_e: kh[skey(he[i])].append(i)
    moved = [(kb[k], kh[k]) for k in kb if k in kh]
    moved_ids = {i for a, b in moved for i in a + b}
    changed = []
    for i in set(be) & set(he):
        a, b = be[i], he[i]
        if (a["confidence"], a.get("reason"), a.get("attrs")) != (b["confidence"], b.get("reason"), b.get("attrs")):
            changed.append(i)
    return {"nodes_added": sorted(hn - bn), "nodes_removed": sorted(bn - hn),
            "edges_added": [i for i in added_e if i not in moved_ids], "edges_removed": [i for i in removed_e if i not in moved_ids],
            "edges_moved": [{"from": a, "to": b} for a, b in moved], "edges_changed": sorted(changed)}


class PRTooLarge(Exception):
    def __init__(self, changed, limit):
        self.changed, self.limit = changed, limit
        super().__init__(f"This PR changes {changed} files; the limit is {limit} (limits.max_changed_files).")


def analyze(project_root, tool_root, config_dir, target, pr, baseline: Graph, freshness, name=None, scratch=None, runner=None, keep=None, target_label=None, pr_label=None):
    """target_label / pr_label: how the report names the base and head (branch names); the revisions actually used are `target` and `pr`."""
    t_start = time.perf_counter()
    root = pathlib.Path(project_root)
    cfg = load_config(config_dir)
    rcfg = risk.from_config(cfg)
    icfg = cfg["graph"]["impact"]
    groups = icfg["consumer_kinds"]
    excluded_kinds = set(icfg["changed_object_excluded_kinds"])
    d_down, d_up = icfg["max_depth_downstream"], icfg["max_depth_upstream"]
    repos = repo_entries(cfg)
    names = [r["name"] for r in repos]
    scratch = pathlib.Path(scratch or root / "out/work/worktrees")
    runner = runner or ScanRunner(tool_root, cfg["dir"], root / "out/work")

    tgt, head_sha = D.resolve(root, target), D.resolve(root, pr)
    mb = D.merge_base(root, tgt, head_sha)
    target_commits = {r["name"]: D.folder_commit(root, tgt, r["path"]) for r in repos}
    warnings = freshness_warnings(freshness, target_commits, mb, tgt, moved_files_that_matter(root, repos, mb, tgt))

    commits = dict(baseline.commits)
    base_frags = M.split_scanner_fragments(baseline, names, commits)
    base_scanner = Graph.from_fragments(list(base_frags.values()))

    all_changed = D.git(root, "diff", "--name-only", "--no-renames", mb, head_sha).splitlines()
    folders = [r["path"].rstrip("/") + "/" for r in repos]
    outside = [f for f in all_changed if not any(f.startswith(x) for x in folders)]          # changed files in no analysed logical repo (a root README, workflows, ...)
    limit = cfg["limits"]["max_changed_files"]
    n_changed = sum(len(D.changes(root, mb, head_sha, r["path"])) for r in repos)
    if n_changed > limit:
        raise PRTooLarge(n_changed, limit)
    # ---- diff + overlay scan of the PR revision (never the baseline store) ----
    t_scan = time.perf_counter()
    files, overlays, head_frags, plan = [], {}, dict(base_frags), {}
    with checkout(root, head_sha, scratch, "pr") as pr_root:
        for r in repos:
            ch = D.changes(root, mb, head_sha, r["path"])
            scanned = [c for c in ch if D.is_scanned(c.path, r.get("include", []), r.get("exclude", []))]
            am = {c.path for c in scanned if c.status in ("A", "M")}
            deleted = {c.path for c in scanned if c.status == "D"}
            touched, overlay = am | deleted, None
            if touched:
                folder = pathlib.Path(pr_root) / r["path"]
                scan_files = set(am)
                if am:
                    overlay = runner.scan(r, folder, only_files=am)
                defs = [n["name"] for n in (overlay or {"nodes": []})["nodes"] if n["kind"] in M.DEFINITION_KINDS]
                extra = M.dependents(base_scanner, r["name"], touched, defs) - touched
                if extra:
                    scan_files |= extra
                    overlay = runner.scan(r, folder, only_files=scan_files)
                    touched |= extra
                head_frags[r["name"]] = M.apply_overlay(base_frags[r["name"]], overlay, touched, D.folder_commit(root, head_sha, r["path"]))
                plan[r["name"]] = {"changed": sorted(am), "deleted": sorted(deleted), "dependents_rescanned": sorted(touched - am - deleted)}
            overlays[r["name"]] = overlay
            for c in ch:
                files.append({"repo": r["name"], "path": c.path, "status": c.status, "scanned": c in scanned,
                              "hunks": [[h.old_range, h.new_range] for h in c.hunks], "change": c})
    t_scan_done = time.perf_counter()
    head_linked = M.relink(head_frags, cfg)
    head = M.full_graph(head_frags, head_linked)
    base = baseline
    delta = graph_delta(base, head)
    head_keys = {edge_key(e) for e in head.edges.values() if e["confidence"] != "UNRESOLVED"}

    # ---- map hunks to nodes ----
    nodes_by_file_b, nodes_by_file_o = collections.defaultdict(list), collections.defaultdict(list)
    for n in base.nodes.values():
        if n.get("file"): nodes_by_file_b[(n["repo"], n["file"])].append(n)
    for rname, ov in overlays.items():
        for n in (ov or {"nodes": []})["nodes"]:
            if n.get("file"): nodes_by_file_o[(n["repo"], n["file"])].append(n)
    objects, file_reports = {}, []
    for f in files:
        fr = {k: v for k, v in f.items() if k != "change"}
        fr["synthetic"] = False
        if not f["scanned"]:
            fr["result"] = "not scanned: no scanner covers this file type/path"
            file_reports.append(fr); continue
        mapped, reason = mapper.map_file(f["change"], nodes_by_file_b[(f["repo"], f["path"])], nodes_by_file_o[(f["repo"], f["path"])], excluded_kinds)
        fr["synthetic"] = any(m.node.get("synthetic") for m in mapped) or any(n.get("synthetic") for n in nodes_by_file_b[(f["repo"], f["path"])] + nodes_by_file_o[(f["repo"], f["path"])])
        fr["result"] = reason or f"{len(mapped)} node(s)"
        fr["no_graph_node"] = reason is not None
        file_reports.append(fr)
        for m in mapped:
            objects[m.node["id"]] = (m, f)

    # ---- unresolved links introduced by the PR ----
    ukey = lambda e: (e["type"], e["source"], e.get("reason"))
    base_unres = {ukey(e) for e in base.edges.values() if e["confidence"] == "UNRESOLVED"}
    new_unres = [e for e in head.edges.values() if e["confidence"] == "UNRESOLVED" and ukey(e) not in base_unres]

    def consumers_of(g, nid, depth):
        best, trunc, cut = T.reach_ex(g, nid, "reverse", depth, EXCL)
        return best, trunc, cut

    results = []
    test_pool = {}
    for nid, (m, f) in sorted(objects.items(), key=lambda kv: (kv[1][0].node["repo"], kv[1][0].node.get("file", ""), kv[1][0].node["location"]["line"])):
        node = m.node
        sources = []
        if m.change in ("modified", "removed") and nid in base.nodes:
            sources.append(("baseline", base))
        if m.change in ("modified", "added") and nid in head.nodes:
            sources.append(("head", head))
        cons: dict[str, dict] = {}
        truncated_down, cut_nodes = False, []
        reach_nodes = {nid}
        for label, g in sources:
            best, trunc, cut = consumers_of(g, nid, d_down)
            truncated_down |= trunc; cut_nodes += cut
            for cid, (conf, path) in best.items():
                if cid == nid: continue
                reach_nodes.add(cid)
                if cid in cons and label == "head": 
                    cons[cid]["also_in_head"] = True; continue
                cons[cid] = {"id": cid, "conf": conf, "path": path, "graph": label, "g": g}
        # classify consumers
        by_group = collections.defaultdict(list)
        tests = []
        for cid, c in cons.items():
            n = c["g"].nodes[cid]
            grp = classify(n["kind"], groups)
            view = {"id": cid, "name": n["name"], "kind": n["kind"], "repo": n["repo"], "file": n.get("file"), "line": (n.get("location") or {}).get("line"),
                    "confidence": c["conf"], "synthetic": n.get("synthetic", False), "found_in": c["graph"],
                    "path": path_view(c["g"], c["path"], head_keys if c["graph"] == "baseline" else None, head)}
            view["broken_by_pr"] = any(h.get("broken_by_pr") for h in view["path"])
            if n["kind"] == "TEST":
                cats = test_categories(c["g"], cid, set(c["g"].nodes) and {k for k in c["g"].nodes if k in reach_nodes or k == nid})
                if not cats:
                    last = view["path"][-1]
                    mm = last["attrs"].get("mapping_method")
                    cats = {"annotation" if mm == "annotation" else "convention" if mm == "naming-convention" else "static-reference"}
                view["mapping"] = min(cats, key=lambda x: TEST_RANK[x])
                view["mapped_by"] = sorted(cats, key=lambda x: TEST_RANK[x])
                tests.append(view)
            elif grp:
                by_group[grp].append(view)
        for v in by_group.values():
            v.sort(key=lambda x: (CONF_ORDER.index(x["confidence"]), x["name"]))
        # dependencies (what the changed object depends on)
        dep_graph = head if (m.change != "removed" and nid in head.nodes) else base
        dbest, dtrunc, dcut = T.reach_ex(dep_graph, nid, "forward", d_up, EXCL)
        deps = []
        for did, (conf, path) in dbest.items():
            if did == nid: continue
            reach_nodes.add(did)
            n = dep_graph.nodes[did]
            grp = classify(n["kind"], groups)
            if grp:
                deps.append({"id": did, "name": n["name"], "kind": n["kind"], "repo": n["repo"], "file": n.get("file"), "line": (n.get("location") or {}).get("line"),
                             "confidence": conf, "path": path_view(dep_graph, path)})
        deps.sort(key=lambda x: (CONF_ORDER.index(x["confidence"]), x["name"]))
        # unresolved: own, in scope, introduced
        new_ids = {e["id"] for e in new_unres}
        own_unres = [e for g in (base, head) for e in g.out.get(nid, []) if e["confidence"] == "UNRESOLVED"]
        seen = set(); own_unres = [cite(base if e["id"] in base.edges else head, e["id"]) for e in own_unres if not (e["id"] in seen or seen.add(e["id"]))]
        own_unres = [u for u in own_unres if u["edge_id"] not in new_ids]      # introduced ones are reported in C1
        introduced = [e for e in new_unres if e["source"] in reach_nodes]
        in_scope = []
        seen = set()
        for g in (base, head):
            for e in T.unresolved_in_scope(g, reach_nodes):
                if e["id"] not in seen and e["id"] not in new_ids and ukey(e) in base_unres:
                    seen.add(e["id"]); in_scope.append(cite(g, e["id"]))
        screens = by_group.get("screen", [])
        facts = {"change": m.change, "kind": node["kind"], "in_critical_list": risk.in_critical_list(rcfg, node["name"]),
                 "has_consumers": any(by_group.get(k) for k in ("screen", "ui_service", "api_endpoint", "business", "sql")),
                 "consumer_count": sum(len(v) for v in by_group.values()),
                 "confirmed_path_reaches_ui": any(s["confidence"] == "CONFIRMED_STATIC" for s in screens),
                 "inferred_path_reaches_ui": any(s["confidence"] == "INFERRED" for s in screens),
                 "reaches_api_endpoint": bool(by_group.get("api_endpoint")),
                 "introduces_unresolved": bool(introduced), "has_own_unresolved": bool(own_unres)}
        rule = risk.select(rcfg, facts)
        attr_changes = []
        if m.change == "modified" and nid in base.nodes and nid in head.nodes:
            ba, ha = base.nodes[nid].get("attrs") or {}, head.nodes[nid].get("attrs") or {}
            attr_changes = [{"attr": k, "before": ba.get(k), "after": ha.get(k)} for k in sorted(set(ba) | set(ha)) if ba.get(k) != ha.get(k)]
        res = {"id": nid, "name": node["name"], "attr_changes": attr_changes, "kind": node["kind"], "repo": node["repo"], "file": node.get("file"),
               "line": (node.get("location") or {}).get("line"), "end_line": (node.get("location") or {}).get("end_line"),
               "change": m.change, "synthetic": node.get("synthetic", False), "mapped_by": m.sides,
               "hunks": [[h.old_range, h.new_range] for h in f["change"].hunks],
               "consumers": dict(by_group), "dependencies": deps, "tests_found": tests,
               "unresolved_own": own_unres, "unresolved_in_scope": in_scope,
               "introduced_unresolved": [{"source": head.nodes[e["source"]]["name"] if e["source"] in head.nodes else e["source"], **cite(head, e["id"])} for e in introduced],
               "facts": facts,
               "depth": {"downstream_limit": d_down, "downstream_truncated": truncated_down, "downstream_stopped_at": sorted(set(cut_nodes)),
                         "upstream_limit": d_up, "upstream_truncated": dtrunc, "upstream_stopped_at": dcut},
               "risk": ({"label": rule["label"], "rule_id": rule["id"], "explain": rule["explain"], "matched": risk.describe_match(rule, facts)} if rule else None),
               "action": rule["action"] if rule else "No risk rule fired. " + ("The object contains unresolved links; review manually." if own_unres else
                                                                              "The graph found no consumers for this object; review manually.")}
        results.append(res)
        for t in tests:
            cur = test_pool.get(t["id"])
            rank = TEST_RANK[t["mapping"]]
            if cur is None or test_sort_key(t) < test_sort_key(cur):
                test_pool[t["id"]] = {**t, "rank": rank, "objects": [res["name"]] + (cur["objects"] if cur else [])}
            else:
                cur["objects"].append(res["name"])

    # new unresolved items (section C), each with the consumers above the broken reference (in the head graph, then baseline for removed nodes)
    new_unres_view = []
    for e in sorted(new_unres, key=lambda e: e["id"]):
        g = head
        best, trunc, cut = T.reach_ex(g, e["source"], "reverse", d_down, EXCL)
        above = []
        for cid, (conf, path) in best.items():
            n = g.nodes[cid]
            grp = classify(n["kind"], groups)
            if cid != e["source"] and grp in ("screen", "api_endpoint", "business", "ui_service"):
                above.append({"name": n["name"], "kind": n["kind"], "file": n.get("file"), "line": (n.get("location") or {}).get("line"),
                              "confidence": conf, "path": path_view(g, path)})
        above.sort(key=lambda x: (x["kind"] != "UI_COMPONENT", x["kind"] != "API_ENDPOINT", x["name"]))
        new_unres_view.append({**cite(head, e["id"]), "source_node": g.nodes[e["source"]]["name"], "source_kind": g.nodes[e["source"]]["kind"],
                               "consumers_above": above, "depth_truncated": trunc})
    # unresolved requests elsewhere that could be hidden consumers of a changed API endpoint
    hidden = []
    if any(o["consumers"].get("api_endpoint") or o["kind"] == "API_ENDPOINT" for o in results):
        for e in head.edges.values():
            if e["type"] == "MAKES_REQUEST" and e["confidence"] == "UNRESOLVED":
                above, _, _ = T.reach_ex(head, e["source"], "reverse", d_down, EXCL)
                hidden.append({**cite(head, e["id"]), "screens_above": sorted(head.nodes[i]["name"] for i in above if head.nodes[i]["kind"] == "UI_COMPONENT")})
    tests_ranked = sorted(test_pool.values(), key=test_sort_key)
    t_end = time.perf_counter()
    if keep is not None:                    # optional: hand the in-memory graphs to the caller (the evaluation harness explains misses with them)
        keep.update(base=base, head=head)
    synthetic_any = any(o["synthetic"] for o in results) or any(f["synthetic"] for f in file_reports)
    return {
        "meta": {"files_outside_analysed_folders": outside, "pr": name or pr, "pr_branch": pr_label or pr, "target": target_label or target, "target_sha": tgt, "pr_sha": head_sha, "merge_base": mb,
                 "baseline_commits": (freshness or {}).get("commits"), "baseline_loaded_at": (freshness or {}).get("loaded_at"),
                 "baseline_mode": (freshness or {}).get("mode"), "target_commits": target_commits, "warnings": warnings,
                 "synthetic_notice": synthetic_any, "scan_plan": plan,
                 "timing_s": {"total_pr_run": round(t_end - t_start, 3), "overlay_scan": round(t_scan_done - t_scan, 3),
                              "analysis_and_report_inputs": round(t_end - t_scan_done, 3)},
                 "depth_limits": {"downstream": d_down, "upstream": d_up}},
        "files": file_reports, "delta": delta, "objects": results, "new_unresolved": new_unres_view, "hidden_consumer_candidates": hidden,
        "tests": tests_ranked, "graph_counts": {"baseline": [len(base.nodes), len(base.edges)], "after_pr": [len(head.nodes), len(head.edges)]},
    }
