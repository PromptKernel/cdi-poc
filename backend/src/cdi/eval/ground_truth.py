"""Ground truth for the evaluation: convert the plain-language input file, validate it against the graph (REPORTING problems, never editing), list candidate names.

The ground truth is fixed BEFORE any evaluation run: eval/ground_truth.yml is committed first, the harness refuses to run unless that file is committed and
unmodified, and it is never edited to match tool output. A workflow is identified by a graph node NAME of one of the workflow kinds (default: screens = UI_COMPONENT,
and API endpoints = API_ENDPOINT).
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


def parse_input_md(text: str) -> dict:
    """Format (see docs/eval/ground_truth_input.template.md): '## <scenario>' headings; bullets are workflow names; free text under a heading is its description;
    a bullet reading 'none' means the scenario is expected to flag no workflow. Lines that are neither are returned in 'unparsed' (never guessed)."""
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
    doc = {"version": 1, "synthetic": True, "source": source, "workflow_kinds": list(kinds or DEFAULT_KINDS),
           "scenarios": {n: {"description": s["description"], "affected_workflows": s["affected_workflows"]} for n, s in parsed["scenarios"].items()}}
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
            problems.append(f"scenario '{sc}' is not defined in cdi/eval/scenarios.py")
        seen = set()
        for w in s["affected_workflows"]:
            if w in seen:
                problems.append(f"{sc}: '{w}' is listed twice")
            seen.add(w)
            if w not in names:
                sub = sorted(n for n in names if w.lower() in n.lower() or n.lower() in w.lower())
                near = list(dict.fromkeys(sub + difflib.get_close_matches(w, list(names), n=3, cutoff=0.6)))[:3]
                problems.append(f"{sc}: '{w}' is not the name of any {'/'.join(gt['workflow_kinds'])} node in the graph" + (f" (similar: {', '.join(near)})" if near else ""))
    return problems


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
        probs = validate(load(a.gt), _graph(a.graph), set(scenarios.SCENARIOS))
        print("\n".join(probs) if probs else "ground truth is consistent with the graph and the scenario list")
        sys.exit(1 if probs else 0)
    else:
        for n, k in sorted(workflow_names(_graph(a.graph), a.kinds.split(",")).items()):
            print(f"{'/'.join(k):<14} {n}")


if __name__ == "__main__":
    main()
