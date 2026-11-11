# Ground truth input (to be filled in by a person; nothing here is filled in)

**What this is.** Before the evaluation harness is run, someone who knows the sample application writes down, **in plain language and without looking at the tool's output**,
what each demo change should affect. The harness then compares the tool's answer with this. It is only meaningful if it is written first and committed before any run.

**How to fill it in.** One block per scenario. A "workflow" is something a user or a system does end to end: a screen, an API endpoint, a stored procedure and everything on the path
between them (for example "the screen that lists the items" or "the call that deletes an item"). Name workflows as you would describe them to a colleague; they are matched to graph nodes
later. If you are unsure, say so in *notes*; an honest "not sure" is more useful than a guess. An empty "should be flagged" list is allowed and means "this change should affect nothing".

Do **not** run the evaluation and do **not** copy anything from a tool report into this file.

Author: ______________________  Date: ______________  Source revision of the sample repository reviewed: ______________________

---

## Scenario 1: `pr-a-sp-body` (a stored procedure's body changes)
Reference (what the demo change does, for orientation only): the list procedure now skips rows with an empty name.

- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

## Scenario 2: `pr-b-view` (a view changes)
Reference: a synthetic view gains one more column.

- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

## Scenario 3: `pr-c-ts-service` (a front-end service method changes)
Reference: a logging line is added to the front-end method that loads the item list.

- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

## Scenario 4: `pr-d-dynamic-sql` (a procedure that builds SQL at run time changes)
Reference: the select list of a procedure that assembles its statement as text is changed.

- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

## Scenario 5: `pr-e-delete-proc` (a stored procedure is deleted)
Reference: a synthetic procedure that other code still calls is removed.

- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

## Scenario 6: `pr-f-route` (an API route is renamed)
Reference: the list route of a controller is renamed, so the front end's request to the old route no longer matches.

- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

---

## Optional extra scenarios (up to four more)
Copy this block for each extra change you would like checked. Describe the change in your own words (what file or object, what edit); the harness needs it to be defined as a scenario in the target repository's `.cdi/scenarios.yml` before it can run.

### Extra scenario A: name: ______________________
- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

### Extra scenario B: name: ______________________
- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

### Extra scenario C: name: ______________________
- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

### Extra scenario D: name: ______________________
- **Change description (your words):**
- **Workflows I believe should be flagged:**
- **Workflows that should NOT be flagged:**
- **Notes:**

---
After you have filled this in: commit it. **Known gap:** `python -m cdi.eval.ground_truth convert` currently reads the older layout in `docs/eval/ground_truth_input.template.md` (`## <scenario>` headings with one bullet per
workflow), not this one, and the "should NOT be flagged" list is new: the metrics do not use it yet. Teaching the converter this layout (and deciding whether the NOT-flagged list becomes an extra false-positive check) is a small follow-up
that should happen before the evaluation is run. The harness refuses to run unless the converted `eval/ground_truth.yml` is committed and unmodified.
