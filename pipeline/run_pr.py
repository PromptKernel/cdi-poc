"""Single local entry point for a PR run (what a CI job would call).
  1. read the baseline graph read-only and check its freshness
  2. run the impact engine for (--target, --pr)
  3. build the comment and the status, publish them through the adapter (file sink by default)
  4. print timing
Advisory by default: the exit code is 0 in every case, including tool failures (those are written as an `error` status and a comment saying the
analysis did not run). Blocking is OFF unless config/ci.yml `blocking.enabled` is true or --blocking is given; even then only a deterministic policy
hit (ci/policy.py) exits 1, never a risk label and never a tool failure.
usage: python -m pipeline.run_pr --target main --pr <branch-or-sha> [--name pr-17] [--baseline neo4j|files] [--out out]
       [--adapter file|azure] [--enable-azure-adapter --pull-request-id N] [--blocking]"""
from __future__ import annotations
import argparse, json, pathlib, sys, time, traceback
import yaml
from ci import adapters, comment, payloads, policy
from impact import cli as impact_cli, diff as D, engine, report
from linker.graphio import load_config

TOOL_ROOT = pathlib.Path(__file__).resolve().parents[1]


class BaselineMissing(Exception):
    pass


def make_basis(root, target, pr, name, ci, mode, baseline_fresh=None):
    def safe(fn, default="?" * 40):
        try:
            return fn()
        except Exception:
            return default
    tsha = safe(lambda: D.resolve(root, target)); psha = safe(lambda: D.resolve(root, pr))
    return {"pr_name": name, "pr_branch": pr, "pr_sha": psha, "target": target, "target_sha": tsha,
            "merge_base": safe(lambda: D.merge_base(root, tsha, psha)), "marker": ci["comment"]["marker"], "mode": mode,
            "baseline_commits": (baseline_fresh or {}).get("commits"), "baseline_loaded_at": (baseline_fresh or {}).get("loaded_at"),
            "baseline_mode": (baseline_fresh or {}).get("mode")}


def highest_label(objs, labels):
    got = [o["risk"]["label"] for o in objs if o["risk"]]
    return min(got, key=lambda l: labels.index(l)) if got else None


def run(args, root=None, tool_root=TOOL_ROOT, now=time.perf_counter, load_baseline=None, adapter=None, ci_override=None):
    """Returns (summary dict, exit code). `ci_override` (tests/programmatic use) is deep-merged over config/ci.yml."""
    t0 = now()
    root = pathlib.Path(root or ".").resolve()
    cfgdir = pathlib.Path(args.config)
    cfg = load_config(cfgdir)
    ci = yaml.safe_load((cfgdir / "ci.yml").read_text())
    for k, v in (ci_override or {}).items():
        ci[k] = {**ci[k], **v} if isinstance(v, dict) else v
    blocking = bool(args.blocking or ci["blocking"]["enabled"])
    mode = "blocking policies enabled" if blocking else "advisory"
    name = args.name or args.pr
    out = pathlib.Path(args.out)
    summary = {"name": name, "mode": mode, "state": None, "skipped": False, "error": None, "violations": [], "post": None}
    basis = make_basis(root, args.target, args.pr, name, ci, mode)
    status_context = ci["status"]["context"]
    maxd = ci["status"]["description_max_chars"]
    try:
        try:
            base, fresh = (load_baseline or impact_cli.load_baseline)(cfg, args.baseline, args.graph)
        except FileNotFoundError as e:           # baseline files absent = no baseline (not a tool failure)
            raise BaselineMissing(f"Baseline files not found ({e.filename}).")
        if not fresh or not base.nodes:
            raise BaselineMissing("No baseline graph was found for the target branch (no freshness record or an empty graph).")
        base.commits = dict(fresh["commits"])
        basis = make_basis(root, args.target, args.pr, name, ci, mode, fresh)
        result = engine.analyze(root, tool_root, cfgdir, args.target, args.pr, base, fresh, name=name)
        out.mkdir(parents=True, exist_ok=True)
        slug = name.replace("/", "_")
        (out / f"report-{slug}.md").write_text(report.render(result))
        (out / f"report-{slug}.json").write_text(report.to_json(result))
        violations = policy.evaluate(result, ci["blocking"]["policies"]) if blocking else []
        md, info = comment.build_report_comment(result, basis, ci["comment"], violations, blocking)
        label = highest_label(result["objects"], load_config_labels(cfgdir))
        desc = (f"{'blocking policy hit: ' + str(len(violations)) if violations else 'advisory'}: {len(result['objects'])} changed object(s)"
                f"{', highest risk label ' + label if label else ', no risk label'}; {len(result['new_unresolved'])} unresolved introduced")
        state = "failed" if (blocking and violations) else "succeeded"
        summary.update(state=state, violations=violations, comment=info, objects=len(result["objects"]), warnings=result["meta"]["warnings"])
    except BaselineMissing as e:
        md = comment.build_skipped_comment(str(e), basis)
        desc, state = "baseline missing, analysis skipped", "notApplicable"
        summary.update(skipped=True, state=state)
    except (Exception, SystemExit) as e:             # the tool itself failed: advisory mode still exits 0
        err = f"{type(e).__name__}: {e}"
        sys.stderr.write(traceback.format_exc())
        md = comment.build_error_comment(err, basis)
        desc, state = f"analysis did not run: {type(e).__name__}", "error"
        summary.update(error=err, state=state)
    status = payloads.status_payload(state, desc, status_context, maxd)
    try:
        adapter = adapter or adapters.build_adapter(args.adapter or ci["adapter"]["default"], ci, out, args.enable_azure_adapter, args.pull_request_id)
        summary["post"] = adapter.post(name, md, status, ci["comment"]["marker"])
    except Exception as e:                           # a posting problem must not fail an advisory run; keep the result in files
        summary["post"] = {"error": f"{type(e).__name__}: {e}"}
        try:
            summary["post"]["fallback"] = adapters.FileSink(out).post(name, md, status, ci["comment"]["marker"])
        except Exception as e2:
            summary["post"]["fallback_error"] = f"{type(e2).__name__}: {e2}"
    summary["duration_s"] = round(now() - t0, 3)
    code = 1 if (blocking and summary["violations"] and state == "failed") else 0
    summary["exit_code"] = code
    return summary, code


def load_config_labels(cfgdir):
    return yaml.safe_load((pathlib.Path(cfgdir) / "risk-rules.yml").read_text())["labels"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="main"); ap.add_argument("--pr", required=True); ap.add_argument("--name")
    ap.add_argument("--baseline", default="neo4j", choices=["neo4j", "files"]); ap.add_argument("--graph", default="out/graph")
    ap.add_argument("--config", default="config"); ap.add_argument("--out", default="out")
    ap.add_argument("--adapter", choices=["file", "azure"]); ap.add_argument("--enable-azure-adapter", action="store_true")
    ap.add_argument("--pull-request-id", type=int); ap.add_argument("--blocking", action="store_true")
    a = ap.parse_args(argv)
    summary, code = run(a)
    print(f"[run_pr] state={summary['state']} mode={summary['mode']} skipped={summary['skipped']} error={summary['error']} exit={code} "
          f"duration={summary['duration_s']} s (measured on this small synthetic sample)")
    print(f"[run_pr] posted: {json.dumps(summary['post'])}")
    for v in summary["violations"]:
        print(f"[run_pr] POLICY {v['policy']}: {v['message']} at {v['repo']}:{v['file']}:{v['line']}")
    sys.exit(code)


if __name__ == "__main__":
    main()
