# Ground truth input (plain language) - TEMPLATE

Copy this to `docs/eval/ground_truth_input.md`, fill it in, then run
`python -m cdi.eval.ground_truth list-workflows` (to copy exact names), `python -m cdi.eval.ground_truth convert docs/eval/ground_truth_input.md eval/ground_truth.yml`,
`python -m cdi.eval.ground_truth validate eval/ground_truth.yml`, and COMMIT `eval/ground_truth.yml` before any evaluation run.

Rules for this file
* One `## <scenario>` heading per scenario. The name must match a branch defined in `backend/src/cdi/eval/scenarios.py` (pr-a-sp-body, pr-b-view, pr-c-ts-service, pr-d-dynamic-sql, pr-e-delete-proc, pr-f-route, or one you add).
* Under it, a bullet per workflow you believe SHOULD be flagged for that change. A workflow is a **screen (UI component name)** or an **API endpoint (controller method name as printed by list-workflows)**.
* Write `- none` if the scenario should flag no workflow. Free text lines under a heading are kept as the scenario's description.
* Anything after ` — `, ` -- ` or ` # ` on a bullet is a comment and is ignored.
* Do not look at the tool's output while writing this; the file is committed before the tool is run and is never edited afterwards.

## pr-a-sp-body
Replace this line with a one-sentence description of the change.
- ExampleScreenName
- Example.Controller.Endpoint()   — optional comment
