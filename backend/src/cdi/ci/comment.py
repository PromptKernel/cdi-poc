"""Build the PR comment (Markdown). Layout: basis and advisory line first, then CONFIRMED consumers and CONFIRMED tests, then unresolved items,
and last the INFERRED consumers and file-convention tests (truncated with counts). The comment is capped at comment.max_chars (config): lower-priority
sections shrink first, and a hard cut keeps the marker, advisory line and basis."""
from __future__ import annotations
from .payloads import marker_text

CONF = "CONFIRMED_STATIC"


def basis_lines(b):
    commits = ", ".join(f"{r} `{(c or '?')[:8]}`" for r, c in sorted((b.get("baseline_commits") or {}).items())) or "none recorded"
    out = [f"**Advisory:** this comment is informational only and does not block the merge (mode: {b.get('mode', 'advisory')}).",
           f"**Basis:** PR commit `{b['pr_sha'][:8]}` (`{b['pr_branch']}`) compared with target `{b['target']}` @ `{b['target_sha'][:8]}` (merge-base `{b['merge_base'][:8]}`); "
           f"baseline graph commits: {commits}; baseline loaded {b.get('baseline_loaded_at') or '?'} ({b.get('baseline_mode') or '?'}).",
           "Results are static-analysis evidence on this repository's own graph; confirmed and inferred links are kept separate."]
    out += [f"**Baseline note:** {n}" for n in b.get("baseline_notes") or []]
    return out


def _header(b, title="Dependency impact"):
    return [marker_text(b["marker"], b["pr_name"]), f"## {title} (advisory)", ""] + basis_lines(b) + [""]


def _cite_hop(h):
    return f"{h['repo']}:{h['file']}:{h['line']}"


def _consumer_line(c):
    last = c["path"][-1] if c["path"] else None
    ev = f" — `{_cite_hop(last)}`" if last else ""
    broken = " ⚠ broken by this PR" if c.get("broken_by_pr") else ""
    return f"- {c['kind']} `{c['name']}`{ev}{broken}"


def _more(n_total, n_shown):
    return f"- … +{n_total - n_shown} more (full report)" if n_total > n_shown else None


def _render(result, b, ccfg, scale, violations, blocking):
    L = ccfg
    lim = lambda k: int(L[k] * scale)
    lines = _header(b)
    meta = result["meta"]
    if meta["warnings"]:
        lines += ["### ⚠ Warnings"] + [f"- {w}" for w in meta["warnings"]] + [""]
    objs = result["objects"]
    if blocking:
        lines += ["### Blocking policies (enabled for this run)"]
        if violations:
            from .policy import group
            for g in group(violations):
                n = len(g["locations"])
                lines.append(f"- ❌ `{g['policy']}`: {g['message']} ({n} location{'s' if n != 1 else ''})")
                for loc in g["locations"]:
                    via = (f" via {', '.join('`'+m+'`' for m in loc['methods'])}" + (f" @{loc['commits'][0][:8]}" if loc["commits"] else "")) if loc["methods"] else " (referenced from)"
                    lines.append(f"  - `{loc['repo']}:{loc['file']}:{loc['line']}`{via}")
                if g["reasons"]:
                    lines.append(f"  - reason: {g['reasons'][0]}")
        else:
            lines.append("- no policy hit")
        lines.append("")
    if not objs:
        nf = [f for f in result["files"] if f.get("no_graph_node")]
        ns = [f for f in result["files"] if not f["scanned"]]
        out = meta.get("files_outside_analysed_folders") or []
        lines += ["### Changed objects", "No changed object mapped to the graph."]
        if result["files"]:
            lines.append(f"Changed files in the analysed folders: {len(result['files'])} ({len(nf)} with no graph node, {len(ns)} not covered by a scanner).")
        if out:
            shown = ", ".join(f"`{f}`" for f in out[:5]) + (f" and {len(out) - 5} more" if len(out) > 5 else "")
            lines.append(f"This pull request changes {len(out)} file(s) outside every folder the scanners analyse: {shown}. They cannot affect the dependency graph.")
        if not result["files"] and not out:
            lines.append("This pull request changes no files.")
        lines += [f"- `{f['repo']}:{f['path']}` — {f['result']}" for f in (nf + ns)[:lim("max_unresolved_items")]]
        return lines + [""]
    lines += [f"### Changed objects ({len(objs)})", "| Object | Kind | Change | Risk (rule that fired) |", "|---|---|---|---|"]
    for o in objs[:max(lim("max_confirmed_consumers"), 3)]:
        rk = f"{o['risk']['label']} (`{o['risk']['rule_id']}`)" if o["risk"] else "NO risk label (no rule fired)"
        lines.append(f"| `{o['name']}`{' (synthetic)' if o['synthetic'] else ''} | {o['kind']} | {o['change']} | {rk} |")
    if len(objs) > max(lim("max_confirmed_consumers"), 3):
        lines.append(f"| … +{len(objs) - max(lim('max_confirmed_consumers'), 3)} more | | | see full report |")
    attr_lines = []
    for o in objs[:max(lim("max_confirmed_consumers"), 3)]:
        if o.get("attr_changes"):
            attr_lines.append(f"`{o['name'].split('.')[-2] + '.' + o['name'].split('.')[-1] if '(' in o['name'] else o['name']}` declared attributes changed: "
                         + "; ".join(f"`{c['attr']}` `{c['before']}` → `{c['after']}`" for c in o["attr_changes"] if c["attr"] != "route_normalized"))
    if attr_lines:                     # a blank line is required: a line directly under a table is rendered as one more table row
        lines += [""] + attr_lines
    lines.append("")

    # 1. CONFIRMED consumers
    lines += ["### Confirmed consumers (every hop a confirmed static link)"]
    any_ = False
    for o in objs:
        conf = [c for g in o["consumers"].values() for c in g if c["confidence"] == CONF]
        conf.sort(key=lambda c: (c["kind"] != "UI_COMPONENT", c["kind"] != "API_ENDPOINT", c["name"]))
        if not conf:
            continue
        any_ = True
        lines.append(f"**`{o['name']}`** ({len(conf)}):")
        shown = conf[:lim("max_confirmed_consumers")]
        lines += [_consumer_line(c) for c in shown]
        m = _more(len(conf), len(shown))
        if m: lines.append(m)
    if not any_:
        lines.append("_None found through confirmed links._")
    lines.append("")

    # 2. CONFIRMED tests (annotation first, then static reference)
    tests = [t for t in result["tests"] if t["rank"] in (0, 1)]
    lines += ["### Tests to run — confirmed (explicit `@covers` annotation first, then direct static references)"]
    shown = tests[:lim("max_confirmed_tests")]
    for t in shown:
        lines.append(f"- `{t['name']}` — `{t['repo']}:{t['file']}:{t['line']}`; mapped by {', '.join(t.get('mapped_by', []))}"
                     + (" ⚠ path broken by this PR" if t.get("broken_by_pr") else ""))
    m = _more(len(tests), len(shown))
    if m: lines.append(m)
    if not tests:
        lines.append("_None._")
    lines.append("")

    # 3. unresolved / not found
    lines += ["### Unresolved / not found"]
    nu = result["new_unresolved"]
    if nu:
        lines.append(f"Introduced by this PR ({len(nu)}):")
        for u in nu[:lim("max_unresolved_items")]:
            above = [x for x in u["consumers_above"] if x["kind"] in ("UI_COMPONENT", "API_ENDPOINT")]
            lines.append(f"- `{u['type']}` {u['source_kind']} `{u['source_node']}` — `{u['repo']}:{u['file']}:{u['line']}` via `{u['method']}` @{u['commit'][:8]}: {u['reason']}"
                         + (f"; above it: {', '.join('`'+x['name'].split('.')[-2]+'.'+x['name'].split('.')[-1]+'`' if x['kind']=='API_ENDPOINT' else '`'+x['name']+'`' for x in above[:3])}" if above else ""))
        m = _more(len(nu), min(len(nu), lim("max_unresolved_items")))
        if m: lines.append(m)
    else:
        lines.append("None introduced by this PR.")
    own = [(o["name"], u) for o in objs for u in o["unresolved_own"]]
    if own:
        lines.append(f"Present on changed objects, not caused by this PR ({len(own)}): graph cannot resolve them, so impact may be under-reported:")
        lines += [f"- `{n}` — `{u['repo']}:{u['file']}:{u['line']}`: {u['reason']}" for n, u in own[:lim("max_unresolved_items")]]
    lines.append("")

    # 4. INFERRED (lower confidence)
    inf = [(o["name"], c) for o in objs for g in o["consumers"].values() for c in g if c["confidence"] == "INFERRED"]
    conv = [t for t in result["tests"] if t["rank"] == 2]
    lines += ["### Lower confidence"]
    if inf:
        lines.append(f"**Inferred consumers ({len(inf)})** — at least one hop is inferred (for example DI-decided dispatch); listed in the full report with the inferred hop flagged.")
        for n, c in inf[:lim("max_inferred_consumers")]:
            lines.append(f"- {c['kind']} `{c['name']}` (via `{n}`)")
        m = _more(len(inf), min(len(inf), lim("max_inferred_consumers")))
        if m: lines.append(m)
        lines.append("")                 # a bold line right under list items would be swallowed by the last item
    if conv:
        lines.append(f"**Naming/file-convention tests ({len(conv)})** — INFERRED; a spec file maps to every method of its source file, so this list over-selects.")
        for t in conv[:lim("max_convention_tests")]:
            lines.append(f"- `{t['name']}`")
        m = _more(len(conv), min(len(conv), lim("max_convention_tests")))
        if m: lines.append(m)
    if not inf and not conv:
        lines.append("None.")
    where = b.get("report_ref") or f"`out/report-{b['pr_name']}.md` and `.json`"
    lines += ["", f"_Full report: {where}. PR run {meta['timing_s']['total_pr_run']} s._"]
    return lines


def build_report_comment(result, basis, ccfg, violations=(), blocking=False):
    """Return (markdown, info). Shrinks lower-priority sections until it fits ccfg['max_chars'], then hard-cuts as a last resort."""
    cap = int(ccfg["max_chars"])
    text, level = "", None
    for scale in (1.0, 0.5, 0.25, 0.1, 0.0):
        text = "\n".join(_render(result, basis, ccfg, scale, list(violations), blocking)).rstrip() + "\n"
        level = scale
        if len(text) <= cap:
            break
    hard = False
    if len(text) > cap:
        hard = True
        keep = "\n".join(_header(basis)) + "\n"
        note = "\n_Comment truncated to fit the configured length cap; see the full report._\n"
        text = (keep + text[len(keep):])[: max(cap - len(note), len(keep))] + note
        text = text[:cap]
    return text, {"chars": len(text), "cap": cap, "scale": level, "hard_truncated": hard}


SKIP_TEXT = {
    "missing": ("Baseline missing, analysis skipped.",
                "No baseline graph exists for the target branch, so the impact of this PR cannot be computed. A baseline is built by the baseline pipeline "
                "(full scan of the target branch, incremental update on merge), not inside a PR run."),
    "schema": ("Baseline unusable (schema version mismatch), analysis skipped.",
               "The stored baseline was written by a different version of the tool, so it is not trusted. Rebuild it with the baseline pipeline; "
               "a PR run never rewrites the baseline."),
    "too_large": ("PR too large, analysis skipped.",
                  "The pull request changes more files than the configured limit (`limits.max_changed_files` in .cdi/config.yml), so no impact analysis "
                  "was attempted. Raise the limit or split the change. This is advisory and does not block the merge."),
}


def build_skipped_comment(reason, basis, kind="missing"):
    head, detail = SKIP_TEXT[kind]
    lines = _header(basis, "Dependency impact — analysis skipped")
    lines += [f"**{head}** {reason}", "", detail, ""]
    return "\n".join(lines).rstrip() + "\n"


def build_error_comment(error_text, basis):
    lines = _header(basis, "Dependency impact — analysis did not run")
    lines += ["**The analysis did not run** because the tool failed. This is advisory and does not block the merge.", "", "```", error_text.strip()[:1500], "```", ""]
    return "\n".join(lines).rstrip() + "\n"
