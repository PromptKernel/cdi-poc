# Evaluation harness

Question answered: *for the synthetic change scenarios, which affected workflows does the tool flag, compared with the workflows its author believes should be flagged?*
Everything is **measured on synthetic data** (the synthetic-extended sample and author-written scenarios). It says nothing about real code bases, and this repository contains no comparison with any outside target.

## Method
1. **Ground truth first.** `docs/eval/ground_truth_input.md` (plain language, written by the repository owner without looking at tool output) is converted by `python -m cdi.eval.ground_truth convert` to
   `eval/ground_truth.yml`, validated (`validate` only *reports* problems; it never edits), and **committed before any evaluation run**. The harness refuses to run unless that file is tracked,
   committed and unmodified, and records its commit and time in the results. It is never edited to match tool output; a suspected error is reported to the owner instead.
2. **Scenarios.** The local branches defined in `backend/src/cdi/eval/scenarios.py` (six by default; more can be added with their ground truth). All are synthetic.
   The harness creates them in a **temporary local clone**, so your branches are never touched, and by default builds the baseline in memory from that clone, so nothing is written to Neo4j.
3. **Workflow.** A graph node of a kind listed in the ground truth file (`workflow_kinds`, default screens `UI_COMPONENT` and API endpoints `API_ENDPOINT`).
   The tool's *reported* workflows are the changed objects that are workflows plus every workflow-kind consumer of a changed object.
4. **Metrics per scenario and overall** (`eval/metrics.py`). With GT = ground truth, R = reported, U = all workflows in the baseline:
   recall = |GT ∩ R| / |GT| (undefined when GT is empty); false-positive share = |R − GT| / |R|; false-positive rate = |R − GT| / |U − GT|. Reported twice: with every link, and with
   CONFIRMED links only (so reliance on INFERRED links is visible). Overall: micro (pooled counts) and macro (mean over scenarios that have ground truth).
   Also reported: number of unresolved and not-found items, PR run duration, baseline freshness (commits per logical repo, load time, stale/fresh).
5. **Misses are explained.** For each ground-truth workflow not reported, the harness states why: the name is not in the graph; no changed object was mapped; an UNRESOLVED link lies on the
   workflow's dependency path (the tool never traverses those); the depth limit was hit; or no path exists at all (not visible to static analysis). Workflows found only through INFERRED links are listed separately.
6. **Output:** `out/eval/summary.md` and `summary.json` (git-ignored). Every number is labelled "measured on synthetic data".

## Run
```
python -m cdi.eval.ground_truth list-workflows        # candidate workflow names from the baseline
python -m cdi.eval.run_eval                           # refuses unless eval/ground_truth.yml is committed and unmodified
python -m cdi.eval.run_eval --baseline neo4j          # use the baseline stored in Neo4j instead of an in-memory one
```

## Limits
* Ground truth and scenarios are written by the tool's author, on a tiny synthetic sample: this measures consistency with the author's expectations, not detection of real defects.
* Granularity is the workflow (screen or endpoint) as defined above; a different definition gives different numbers.
* The baseline in a default run is rebuilt from the clone, so freshness is "fresh" by construction; use `--baseline neo4j` to evaluate a stored baseline.
* Timing is for a very small repository on one machine.
* Metrics that need real workflows or real history (a drop in real regression defects, how well important workflows are covered by mapped tests, how freshness evolves over time) are not measurable here.
