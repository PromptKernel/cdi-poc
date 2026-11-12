"""Ground truth for the evaluation: convert the plain-language input file, validate it against the graph (REPORTING problems, never editing), list candidate names.

The ground truth is fixed BEFORE any evaluation run: eval/ground_truth.yml is committed first, the harness refuses to run unless that file is committed and
unmodified, and it is never edited to match tool output. A workflow is identified by a graph node NAME of one of the workflow kinds (default: screens = UI_COMPONENT,
and API endpoints = API_ENDPOINT).
Two input layouts are read: the older one (docs/eval/ground_truth_input.template.md: '## <scenario>' headings with one bullet per workflow) and the current one
(docs/eval/ground_truth_input.md: '## Scenario N: `<name>`' blocks with the bold-labelled fields 'Change description', 'Workflows I believe should be flagged',
'Workflows that should NOT be flagged' and 'Notes'). A blank field is reported as missing, never filled in; write 'none' for a deliberately empty list.
usage: python -m cdi.eval.ground_truth convert  <input.md> <ground_truth.yml>
       python -m cdi.eval.ground_truth validate <ground_truth.yml> [--graph out/graph]
       python -m cdi.eval.ground_truth list-workflows [--graph out/graph]"""
from __future__ import annotations
import argparse, difflib, pathlib, re, sys
import yaml

DEFAULT_KINDS = ["UI_COMPONENT", "API_ENDPOINT"]
NONE_WORDS = {"none", "(none)", "nothing", "no workflows", "no workflow", "(no workflows)", "n/a", "-"}


def _clean(item: str) -> str:
    item = item.strip().strip("`").strip()
    item = re.split(r"\s+(?:—|--|–|#)\s+", item, maxsplit=1)[0]          # trailing comment after an em dash, '--' or '#'
    return item.strip().strip("`").strip()


FIELD_LABELS = {"description": "change description", "flagged": "workflows i believe should be flagged",
                "not_flagged": "workflows that should not be flagged", "notes": "notes"}
REQUIRED = ("description", "flagged", "not_flagged")          # notes are optional
FIELD_RE = re.compile(r"^\s*[-*]\s+\*\*(.+?)(?::\*\*|\*\*:)\s*(.*)$")
BLOCK_RE = re.compile(r"^#{2,3}\s+((?:Scenario\s+\d+|Extra scenario\s+[A-Za-z0-9]+))\b\s*:?\s*(.*?)\s*$")


def _blank(text: str) -> bool:
    return not text.strip() or re.fullmatch(r"[_\s]*", text.strip()) is not None


def _split_top_level(text: str) -> list[str]:
    """Split on ';' and on ',' outside parentheses and backticks (method signatures contain commas)."""
    parts, cur, depth, tick = [], [], 0, False
    for ch in text:
        if ch == "`":
            tick = not tick
        elif not tick and ch == "(":
            depth += 1
        elif not tick and ch == ")":
            depth = max(0, depth - 1)
        if ch == ";" or (ch == "," and depth == 0 and not tick):
            parts.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [x for x in (p.strip() for p in parts) if x]


def _list_value(lines: list[str]) -> tuple[list[str], bool, bool]:
    """(items, declared_none, blank) from the lines of a list field (inline text and/or nested bullets)."""
    items, none, any_text = [], False, False
    for ln in lines:
        if _blank(ln):
            continue
        any_text = True
        b = re.match(r"^\s*[-*]\s+(.*)$", ln)
        chunks = [b.group(1)] if b else _split_top_level(ln)
        for ch in chunks:
            it = _clean(ch)
            if _blank(it):
                continue
            if it.lower() in NONE_WORDS:
                none = True
            else:
                items.append(it)
    return list(dict.fromkeys(items)), none, not any_text


def _parse_blocks(text: str) -> dict:
    header, blocks, cur = {}, [], None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = BLOCK_RE.match(line)
        if m:
            cur = {"heading": m.group(1), "rest": m.group(2), "fields": {}, "field": None}
            blocks.append(cur); continue
        if re.match(r"^#{1,6}\s", line) or line.strip() == "---":          # any other heading or a rule ends the block
            cur = None
            continue
        if cur is None:
            h = re.match(r"^\s*Author:\s*(.*?)\s+Date:\s*(.*?)\s+Source revision[^:]*:\s*(.*?)\s*$", line)
            if h:
                header = {"author": h.group(1), "date": h.group(2), "source_revision": h.group(3)}
            continue
        f = FIELD_RE.match(line)
        if f:
            label = re.sub(r"\s*\([^)]*\)\s*$", "", f.group(1).strip().lower())          # "Change description (your words)" -> "change description"
            key = next((k for k, v in FIELD_LABELS.items() if label == v), None)
            cur["field"] = key
            if key:
                cur["fields"][key] = [f.group(2)]
            continue
        if cur["field"]:
            cur["fields"][cur["field"]].append(line)
    return {"header": header, "blocks": blocks}


def parse_input_md_blocks(text: str) -> dict:
    """The current layout. Problems (missing fields, contradictions, blank names) go to 'unparsed'; nothing is guessed or filled in."""
    parsed = _parse_blocks(text)
    scenarios, unparsed, header = {}, [], parsed["header"]
    for b in parsed["blocks"]:
        tick = re.search(r"`([^`]+)`", b["rest"])
        nm = re.search(r"name:\s*(.*)$", b["rest"])
        name = (tick.group(1) if tick else (nm.group(1) if nm else "")).strip().strip("`")
        name = "" if _blank(name) else name
        fields = b["fields"]
        flagged, f_none, f_blank = _list_value(fields.get("flagged", []))
        notflag, n_none, n_blank = _list_value(fields.get("not_flagged", []))
        desc = " ".join(x.strip() for x in fields.get("description", []) if not _blank(x)).strip()
        notes = " ".join(x.strip() for x in fields.get("notes", []) if not _blank(x)).strip()
        all_blank = not name and not desc and f_blank and n_blank and not notes
        if all_blank:
            if b["heading"].lower().startswith("scenario"):
                unparsed.append(f"{b['heading']}: empty (no name and no fields)")
            continue                                           # an unused optional extra scenario
        label = name or b["heading"]
        if not name:
            unparsed.append(f"{b['heading']}: fields are filled but the scenario name is missing")
            continue
        for key, blank in (("description", not desc), ("flagged", f_blank), ("not_flagged", n_blank)):
            if blank:
                hint = " (write 'none' if the list is deliberately empty)" if key != "description" else ""
                unparsed.append(f"{label}: missing field '{FIELD_LABELS[key]}'{hint}")
        if flagged and f_none:
            unparsed.append(f"{label}: both workflows and 'none' were given under 'should be flagged'")
        if notflag and n_none:
            unparsed.append(f"{label}: both workflows and 'none' were given under 'should NOT be flagged'")
        overlap = sorted(set(flagged) & set(notflag))
        if overlap:
            unparsed.append(f"{label}: listed both as flagged and as NOT flagged: {', '.join(overlap)}")
        if name in scenarios:
            unparsed.append(f"{label}: the scenario appears twice")
        scenarios[name] = {"description": desc, "affected_workflows": flagged, "not_flagged_workflows": notflag, "notes": notes}
    for key in ("author", "date", "source_revision"):
        if _blank(header.get(key, "")):
            unparsed.append(f"header: '{key}' is not filled in")
    return {"scenarios": scenarios, "unparsed": unparsed, "header": {k: v for k, v in header.items() if not _blank(v)}}


def parse_input_md(text: str) -> dict:
    """Format (see docs/eval/ground_truth_input.template.md): '## <scenario>' headings; bullets are workflow names; free text under a heading is its description;
    a bullet reading 'none' means the scenario is expected to flag no workflow. Lines that are neither are returned in 'unparsed' (never guessed)."""
    if "**Workflows I believe should be flagged" in text:
        return parse_input_md_blocks(text)
    scenarios: dict[str, dict] = {}
    cur = None
    unparsed: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1).strip().strip("`")
            scenarios.setdefault(cur, {"description": [], "workflows": [], "empty": False})
            continue
        if cur is None or not line.strip() or line.startswith("# ") or line.strip().startswith(("<!--", "-->")):
            continue
        b = re.match(r"^\s*[-*]\s+(.*)$", line)
        if b:
            item = _clean(b.group(1))
            if item.lower() in NONE_WORDS:
                scenarios[cur]["empty"] = True
            elif item:
                scenarios[cur]["workflows"].append(item)
        elif re.match(r"^\s*(description|notes?)\s*:", line, re.I):
            scenarios[cur]["description"].append(line.split(":", 1)[1].strip())
        else:
            scenarios[cur]["description"].append(line.strip())
    out = {"scenarios": {}, "unparsed": unparsed}
    for name, s in scenarios.items():
        if s["workflows"] and s["empty"]:
            unparsed.append(f"{name}: both workflows and 'none' were given")
        out["scenarios"][name] = {"description": " ".join(s["description"]).strip(), "affected_workflows": list(dict.fromkeys(s["workflows"]))}
    return out


def to_yaml(parsed: dict, source: str = "docs/eval/ground_truth_input.md", kinds=None) -> str:
    def entry(s):
        e = {"description": s["description"], "affected_workflows": s["affected_workflows"]}
        if "not_flagged_workflows" in s:
            e["not_flagged_workflows"] = s["not_flagged_workflows"]
        if s.get("notes"):
            e["notes"] = s["notes"]
        return e
    doc = {"version": 1, "synthetic": True, "source": source, **{k: v for k, v in (parsed.get("header") or {}).items()},
           "workflow_kinds": list(kinds or DEFAULT_KINDS), "scenarios": {n: entry(s) for n, s in parsed["scenarios"].items()}}
    header = ("# EVALUATION GROUND TRUTH. Converted from the plain-language input; committed BEFORE any evaluation run and never edited to match tool output.\n"
              "# All scenarios and workflows are SYNTHETIC. A workflow is a graph node NAME of one of workflow_kinds.\n")
    return header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)


def load(path) -> dict:
    d = yaml.safe_load(pathlib.Path(path).read_text())
    if d.get("version") != 1 or "scenarios" not in d:
        raise ValueError(f"{path}: not a version-1 ground truth file")
    d.setdefault("workflow_kinds", list(DEFAULT_KINDS))
    for n, s in d["scenarios"].items():
        s["affected_workflows"] = list(s.get("affected_workflows") or [])
        s["not_flagged_workflows"] = list(s.get("not_flagged_workflows") or [])
    return d


def workflow_names(graph, kinds) -> dict:
    """name -> [kinds] for every node of a workflow kind."""
    out: dict[str, list] = {}
    for n in graph.nodes.values():
        if n["kind"] in kinds:
            out.setdefault(n["name"], []).append(n["kind"])
    return out


def validate(gt: dict, graph, known_scenarios) -> list[str]:
    """Problems with the ground truth. REPORTED to the owner; this never changes the file."""
    names = workflow_names(graph, gt["workflow_kinds"])
    problems = []
    for sc, s in gt["scenarios"].items():
        if sc not in known_scenarios:
            problems.append(f"scenario '{sc}' is not defined in .cdi/scenarios.yml")
        seen = set()
        for w in s["affected_workflows"]:
            if w in seen:
                problems.append(f"{sc}: '{w}' is listed twice")
            seen.add(w)
            if w not in names:
                problems.append(_unknown(sc, w, names, gt["workflow_kinds"], ""))
        seen = set()
        for w in s.get("not_flagged_workflows", []):
            if w in seen:
                problems.append(f"{sc}: '{w}' is listed twice under NOT flagged")
            seen.add(w)
            if w not in names:
                problems.append(_unknown(sc, w, names, gt["workflow_kinds"], " (NOT-flagged list)"))
            if w in s["affected_workflows"]:
                problems.append(f"{sc}: '{w}' is listed as both flagged and NOT flagged")
    return problems


def _unknown(sc, w, names, kinds, where):
    sub = sorted(n for n in names if w.lower() in n.lower() or n.lower() in w.lower())
    near = list(dict.fromkeys(sub + difflib.get_close_matches(w, list(names), n=3, cutoff=0.6)))[:3]
    return f"{sc}: '{w}' is not the name of any {'/'.join(kinds)} node in the graph{where}" + (f" (similar: {', '.join(near)})" if near else "")


def _graph(graph_dir):
    from cdi.linker.graphio import Graph, load_config, load_fragments
    cfg = load_config()
    return Graph.from_fragments(load_fragments(graph_dir, [r["name"] for r in cfg["repos"]["repos"]], include_linked=True))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert"); c.add_argument("input"); c.add_argument("output")
    v = sub.add_parser("validate"); v.add_argument("gt"); v.add_argument("--graph", default="out/graph")
    l = sub.add_parser("list-workflows"); l.add_argument("--graph", default="out/graph"); l.add_argument("--kinds", default=",".join(DEFAULT_KINDS))
    a = ap.parse_args(argv)
    if a.cmd == "convert":
        parsed = parse_input_md(pathlib.Path(a.input).read_text())
        if parsed["unparsed"] or not parsed["scenarios"]:
            sys.exit("could not convert (nothing is written):\n  " + "\n  ".join(parsed["unparsed"] or ["no '## <scenario>' headings found"]))
        pathlib.Path(a.output).write_text(to_yaml(parsed, a.input))
        print(f"wrote {a.output}: {len(parsed['scenarios'])} scenario(s). Next: validate, commit it, and only then run the evaluation.")
    elif a.cmd == "validate":
        from cdi.eval import scenarios
        probs = validate(load(a.gt), _graph(a.graph), set(scenarios.load_scenarios()))
        print("\n".join(probs) if probs else "ground truth is consistent with the graph and the scenario list")
        sys.exit(1 if probs else 0)
    else:
        for n, k in sorted(workflow_names(_graph(a.graph), a.kinds.split(",")).items()):
            print(f"{'/'.join(k):<14} {n}")


if __name__ == "__main__":
    main()
