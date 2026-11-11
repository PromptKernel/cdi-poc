"""Render the impact result as Markdown (and JSON). Every claim cites a stored edge: file:line, analysis method and commit."""
from __future__ import annotations
import json
MAX_DEPS_IN_MD = 12


def hop_line(h):
    s = (f"`{h['type']}` [{h['confidence']}] {h['source_kind']} `{h['source']}` → {h['target_kind']} `{h['target']}` — "
         f"{h['repo']}:{h['file']}:{h['line']} via `{h['method']}` @{(h['commit'] or '')[:8]}")
    if h.get("synthetic"):
        s += " (synthetic)"
    if h["confidence"] != "CONFIRMED_STATIC" and h.get("reason"):
        s += f" — reason: {h['reason']}"
    if h.get("broken_by_pr"):
        s += "  ⚠ **no longer holds after this PR**"
        r = h.get("replacement")
        if r:
            s += f" (now `{r['type']}` [{r['confidence']}] at {r['repo']}:{r['file']}:{r['line']}: {r.get('reason') or r['target']})"
    return s


def path_block(path, indent="    "):
    return "\n".join(f"{indent}- {hop_line(h)}" for h in path)


def label_text(o):
    r = o["risk"]
    if not r:
        return "**NO risk label** — no rule fired"
    return f"**{r['label']}** — rule `{r['rule_id']}`: {r['explain']} (matched: {r['matched']})"


def render(res):
    m = res["meta"]
    L = []
    a = L.append
    a(f"# Impact report: {m['pr']} → {m['target']}")
    a("")
    if m["synthetic_notice"]:
        a("> **Synthetic data.** At least one changed file is flagged synthetic by this repository's configuration (written for demonstration, not by the project's authors); "
          "objects marked *synthetic* below. Results on synthetic files say nothing about accuracy on real code.")
    else:
        a("> Static-analysis evidence only: every claim cites a stored edge, and none of it is validated against other code bases.")
    a("")
    if m["warnings"]:
        a("## ⚠ Warnings")
        for w in m["warnings"]:
            a(f"- {w}")
        a("")
    t = m["timing_s"]
    a("## Run")
    a(f"- PR branch `{m['pr_branch']}` @ `{m['pr_sha'][:8]}`; target `{m['target']}` @ `{m['target_sha'][:8]}`; merge-base `{m['merge_base'][:8]}` (diff is merge-base..PR, three-dot)")
    a(f"- Baseline graph (read-only): commits {json.dumps({k: v[:8] for k, v in (m['baseline_commits'] or {}).items()})}, loaded {m['baseline_loaded_at']} ({m['baseline_mode']})")
    a(f"- Graph before/after PR (in memory; the stored baseline is not modified): nodes/edges {res['graph_counts']['baseline']} → {res['graph_counts']['after_pr']}")
    a(f"- Depth limits (config, placeholder): downstream {m['depth_limits']['downstream']}, upstream {m['depth_limits']['upstream']}")
    a(f"- **PR run duration {t['total_pr_run']} s** (overlay scan {t['overlay_scan']} s; rest = query, mapping, traversal) (measured on this repository and machine only)")
    if m["scan_plan"]:
        a(f"- Overlay scan plan: {json.dumps(m['scan_plan'])}")
    a("")
    objs = res["objects"]
    a("## Summary")
    a("")
    a("| # | Changed object | Kind | Repo | Change | Risk (rule) | Consumers (screens / endpoints / methods / SQL) | Synthetic |")
    a("|---|---|---|---|---|---|---|---|")
    for i, o in enumerate(objs, 1):
        c = o["consumers"]
        cnt = " / ".join(str(len(c.get(k, []))) for k in ("screen", "api_endpoint", "business", "sql"))
        rk = f"{o['risk']['label']} (`{o['risk']['rule_id']}`)" if o["risk"] else "NO risk label"
        a(f"| {i} | `{o['name']}` | {o['kind']} | {o['repo']} | {o['change']} | {rk} | {cnt} | {'yes' if o['synthetic'] else 'no'} |")
    if not objs:
        a("| – | no changed object mapped to the graph | | | | | | |")
    a("")
    a("## Changed files")
    a("")
    for f in res["files"]:
        h = ", ".join(f"old {x[0]} → new {x[1]}" for x in f["hunks"]) or "whole file"
        flag = " **NO GRAPH NODE**" if f.get("no_graph_node") else ""
        a(f"- `{f['repo']}:{f['path']}` ({f['status']}){' synthetic' if f['synthetic'] else ''} — {f['result']}{flag}; hunks: {h}")
    a("")
    d = res["delta"]
    a("## Graph delta (baseline → after PR)")
    a(f"- nodes added {len(d['nodes_added'])}, removed {len(d['nodes_removed'])}; edges added {len(d['edges_added'])}, removed {len(d['edges_removed'])}, "
      f"moved (same link, different line) {len(d['edges_moved'])}, changed (confidence/reason/attrs) {len(d['edges_changed'])}")
    for k in ("nodes_removed", "nodes_added", "edges_removed", "edges_added", "edges_changed"):
        for i in d[k][:10]:
            a(f"  - {k}: `{i}`")
        if len(d[k]) > 10:
            a(f"  - {k}: … {len(d[k]) - 10} more (see JSON)")
    a("")
    a("## Changed objects")
    for i, o in enumerate(objs, 1):
        a("")
        a(f"### {i}. `{o['name']}`")
        a(f"- **Changed object:** `{o['name']}` — **kind:** {o['kind']} — **repo:** {o['repo']} — **change:** {o['change']}{' — **synthetic**' if o['synthetic'] else ''}")
        a(f"- **Evidence:** {o['repo']}:{o['file']}:{o['line']}–{o['end_line']}; hunks (old/new): {o['hunks']}; matched on the {'/'.join(o['mapped_by'])} side")
        if o.get("attr_changes"):
            a("- **Declared attributes changed:** " + "; ".join(f"`{c['attr']}`: `{c['before']}` → `{c['after']}`" for c in o["attr_changes"]))
        a(f"- **Risk:** {label_text(o)}")
        a(f"- **Required developer action:** {o['action']}")
        c = o["consumers"]
        names = lambda k: ", ".join(f"`{x['name']}` [{x['confidence'][:4]}]" for x in c.get(k, [])) or "none found"
        a(f"- **Potential consumers:** screens: {names('screen')}; UI services: {names('ui_service')}; API endpoints: {names('api_endpoint')}; business/data-access methods: {len(c.get('business', []))}; SQL objects: {names('sql')}")
        counts = {k: sum(1 for g in c.values() for x in g if x["confidence"] == k) for k in ("CONFIRMED_STATIC", "INFERRED")}
        a(f"- **Confidence:** mapping of hunks to this node: from scanner locations; consumer paths: {counts['CONFIRMED_STATIC']} confirmed, {counts['INFERRED']} inferred; "
          f"unresolved links on/under it: {len(o['unresolved_own'])} own, {len(o['introduced_unresolved'])} introduced by this PR")
        dp = o["depth"]
        if dp["downstream_truncated"]:
            a(f"- ⚠ **Downstream traversal stopped at the depth limit ({dp['downstream_limit']})** at: {', '.join(dp['downstream_stopped_at'][:5])}; consumers beyond it are NOT listed.")
        if dp["upstream_truncated"]:
            a(f"- ⚠ **Upstream traversal stopped at the depth limit ({dp['upstream_limit']})**; dependencies beyond it are NOT listed.")

    def section(title, conf, blurb):
        a("")
        a(f"## {title}")
        a(blurb)
        a("Reading a hop: `A → B` means A depends on B (the stored edge direction). A path starts at the changed object and walks outward through its consumers or dependencies.")
        any_ = False
        for o in objs:
            items = [x for g in o["consumers"].values() for x in g if x["confidence"] == conf]
            deps = [x for x in o["dependencies"] if x["confidence"] == conf]
            if not items and not deps:
                continue
            any_ = True
            a("")
            a(f"### `{o['name']}` ({o['change']})")
            if items:
                a(f"**Consumers — who depends on it ({len(items)}):**")
                for x in sorted(items, key=lambda x: (x["kind"] != "UI_COMPONENT", x["kind"] != "API_ENDPOINT", x["name"])):
                    a(f"- {'**BROKEN BY THIS PR (held in the baseline, not after it)** — ' if x['broken_by_pr'] else ''}{x['kind']} `{x['name']}` — found in the {x['found_in']} graph")
                    a(path_block(x["path"]))
            if deps:
                a(f"**Dependencies — what it depends on ({len(deps)}; first {min(len(deps), MAX_DEPS_IN_MD)} shown):**")
                for x in deps[:MAX_DEPS_IN_MD]:
                    a(f"- {x['kind']} `{x['name']}`")
                    a(path_block(x["path"]))
        if not any_:
            a("")
            a("_None._")

    section("A. CONFIRMED paths", "CONFIRMED_STATIC", "Every hop is a confirmed static link (resolved symbol, literal-matched route or name, table reference in DDL).")
    section("B. INFERRED paths", "INFERRED", "At least one hop is inferred (for example interface dispatch decided by runtime dependency injection). The inferred hop is flagged in each path.")
    a("")
    a("## C. UNRESOLVED / not found")
    a("Nothing below is a confirmed or inferred path. These are places where the graph is incomplete or a reference does not resolve.")
    a("")
    a("### C1. Introduced by this PR (present after the PR, absent in the baseline)")
    if not res["new_unresolved"]:
        a("_None._")
    for u in res["new_unresolved"]:
        a(f"- `{u['type']}` from {u['source_kind']} `{u['source_node']}` — {u['repo']}:{u['file']}:{u['line']} via `{u['method']}` @{u['commit'][:8]}{' (synthetic)' if u['synthetic'] else ''}")
        a(f"  - reason: {u['reason']}")
        if u["evidence"]:
            a(f"  - source: `{u['evidence'][:120]}`")
        if u["attrs"].get("referenced_from"):
            a(f"  - referenced from: {', '.join(u['attrs']['referenced_from'])}")
        if u["consumers_above"]:
            a("  - consumers above the broken reference (screens / endpoints / methods):")
            for x in u["consumers_above"][:12]:
                a(f"    - {x['kind']} `{x['name']}` [{x['confidence']}] — {x['repo'] if 'repo' in x else ''}{x['file']}:{x['line']}")
                a(path_block(x["path"], "        "))
        else:
            a("  - no screen/endpoint/method above it was found through resolved links")
        if u["depth_truncated"]:
            a("  - ⚠ traversal above this reference stopped at the depth limit")
    a("")
    a("### C2. Pre-existing unresolved links on or under the changed objects (already present in the baseline)")
    any_ = False
    for o in objs:
        for u in o["unresolved_own"] + [x for x in o["unresolved_in_scope"] if x not in o["unresolved_own"]]:
            any_ = True
            a(f"- `{o['name']}` → `{u['type']}` {u['repo']}:{u['file']}:{u['line']} via `{u['method']}` @{u['commit'][:8]} — reason: {u['reason']}")
    if not any_:
        a("_None._")
    a("")
    a("### C3. Context: unresolved requests that might consume a changed endpoint (not linked; not claimed as consumers)")
    if not res["hidden_consumer_candidates"]:
        a("_None, or no API endpoint is affected._")
    for u in res["hidden_consumer_candidates"]:
        sc = f"; screen(s) that call it: {', '.join(u['screens_above'])}" if u["screens_above"] else ""
        a(f"- {u['source']} — {u['repo']}:{u['file']}:{u['line']} — reason: {u['reason']}{sc}")
    a("")
    a("## Tests to run")
    a("Ranked: (1) explicit `@covers` annotation (CONFIRMED), (2) a test that statically references an affected object (CONFIRMED), (3) naming/file-convention mappings (INFERRED).")
    by = {0: [], 1: [], 2: []}
    for t_ in res["tests"]:
        by[t_["rank"]].append(t_)
    for rank, title in ((0, "1. Annotation-based (CONFIRMED)"), (1, "2. Static reference from the test (CONFIRMED)")):
        a("")
        a(f"**{title}**")
        for t_ in by[rank]:
            a(f"- `{t_['name']}` — {t_['repo']}:{t_['file']}:{t_['line']}; mapped by: {', '.join(t_.get('mapped_by', []))}; for changed object(s): {', '.join(sorted(set(t_['objects'])))}; path confidence {t_['confidence']}"
              f"{'; ⚠ the path to it is broken by this PR' if t_.get('broken_by_pr') else ''}")
            a(path_block(t_["path"][-1:], "    "))
        if not by[rank]:
            a("_None._")
    a("")
    a(f"**3. Naming / file-convention (INFERRED) — grouped separately: a spec file maps to every method of the same-named source file, so this list fans out and over-selects.** ({len(by[2])} tests)")
    for t_ in by[2]:
        a(f"- `{t_['name']}` — {t_['repo']}:{t_['file']}:{t_['line']}; via {t_['path'][-1]['target']} ({t_['path'][-1]['attrs'].get('mapping_method')})")
    a("")
    a("---")
    a("Risk labels come only from the `risk` section of `.cdi/config.yml` (first matching rule; no catch-all). An object with no matching rule has no label. The default critical list is a placeholder.")
    return "\n".join(L) + "\n"


def to_json(res):
    return json.dumps(res, indent=2, default=list)
