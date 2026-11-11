# CI simulation (advisory PR check)

No Azure DevOps resources exist for this PoC. The PR check is **simulated locally**: `pipeline/run_pr.py` does everything a CI job would do and writes the
result to files. `config.example/optional/azure/azure-pipelines.yml` is a thin wrapper around it and the Azure DevOps adapter is code that **has never been executed**. **None of the
payload shapes below were tested against a real service.**

## Entry point
`backend/scripts/run_pr.sh --target main --pr <branch|sha> [--name pr-17] [--baseline neo4j|files] [--out out] [--blocking]`
(= `python -m cdi.pipeline.run_pr`). Steps: read the baseline graph read-only and check its freshness, run the impact engine, build the comment and the
status, publish through the adapter, print timing.

| Situation | Comment | Status `state` | Exit code |
|---|---|---|---|
| Normal run (advisory) | impact comment | `succeeded` | **0** |
| Baseline missing (no freshness record or empty graph) | "Baseline missing, analysis skipped"; **no baseline is built inside a PR run** | `notApplicable` | **0** |
| The tool itself fails (store unreachable, scanner error, ...) | "The analysis did not run" plus the error text | `error` | **0** |
| Blocking enabled and a deterministic policy hits | impact comment plus the policy hits with file:line | `failed` | **1** |

Advisory mode exits 0 in every case. Even with blocking enabled, only a policy hit exits 1; a tool failure or a risk label never does.
A problem while posting (for example a disabled adapter) is reported in the run summary and does not fail an advisory run.

## Outputs (default adapter: local file sink)
* `out/pr-comment.md` - the comment, Markdown. First line is the stable marker `<!-- cdi-poc:impact-report:v1 pr=<name> -->`.
* `out/pr-status.json` - `{"simulated": true, "shape_verified_against_real_service": false, "thread": <thread body>, "status": <status body>}`.
* `out/report-<name>.md` / `.json` - the full impact report.
The file sink overwrites on every run.

Every comment states its **basis**: the PR commit, the target branch commit and merge-base, the baseline commit ID **per logical repo**, when and how the baseline
was loaded, and an **advisory** line.

## Comment layout and length
1. marker, advisory line, basis, warnings (stale baseline, PR based on an older target)
2. changed objects with the risk label **and the rule that fired** (or "NO risk label")
3. **Confirmed consumers** (every hop a confirmed static link), each with a file:line
4. **Tests to run - confirmed**: explicit `@covers` annotation first, then direct static references
5. **Unresolved / not found**: introduced by the PR (with file:line, method, commit, reason) and pre-existing on the changed objects
6. **Lower confidence** last: INFERRED consumers and naming/file-convention tests, truncated with counts ("+N more")
`<details>` (collapsing) is not used: none of the pages consulted says PR comments render it, so the lower-priority parts are truncated with counts instead.

**Length limit.** None of the REST pages consulted states a maximum length for comment content or for a status description, and the Azure DevOps "object limits" page
lists no pull-request comment limit. the `ci` section of `.cdi/config.yml` therefore applies a conservative cap of our own (`comment.max_chars: 20000`, `status.description_max_chars: 300`,
both marked *placeholder, unvalidated*). Lower-priority sections shrink first; if the comment still exceeds the cap it is hard-cut, keeping the marker, advisory line and basis.

## Payload shapes (Azure DevOps REST, api-version 7.1)
Documents consulted (fetched during implementation):
* Create a thread: https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-threads/create?view=azure-devops-rest-7.1
  `POST https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repositoryId}/pullRequests/{pullRequestId}/threads?api-version=7.1`;
  body `comments[] {parentCommentId, content, commentType}`, `status`, `properties`. Enumerations: `CommentThreadStatus` (`active`, `fixed`, `closed`, ...), `CommentType` (`text`, ...).
  Note: the page's *example requests* use integers (`"status": 1`, `"commentType": 1`) while its definitions list the names; we send the names. Unverified.
* List threads (used to find our own thread): https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-threads/list?view=azure-devops-rest-7.1
  `GET .../pullRequests/{pullRequestId}/threads?api-version=7.1` returns `value[]` of threads with `comments[].content`, `isDeleted`, `properties`.
* Update a comment (used to update our own thread): https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-thread-comments/update?view=azure-devops-rest-7.1
  `PATCH .../threads/{threadId}/comments/{commentId}?api-version=7.1` with a body containing `content`.
* Update a thread (consulted; not used - it updates the thread, not a comment's text): https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-threads/update?view=azure-devops-rest-7.1
* Create a status: https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-statuses/create?view=azure-devops-rest-7.1
  `POST .../pullRequests/{pullRequestId}/statuses?api-version=7.1`; body `state`, `description`, `context {name, genre}`, optional `targetUrl`.
  "The only required field for the status is `Context.Name` that uniquely identifies the status." `GitStatusState`: `notSet`, `pending`, `succeeded`, `failed`, `error`, `notApplicable`.
* Pipeline variables and the access token: https://learn.microsoft.com/en-us/azure/devops/pipelines/build/variables?view=azure-devops&tabs=yaml
  (`System.PullRequest.PullRequestId`, `.SourceCommitId`, `.targetBranchName`; `System.AccessToken` must be mapped into a step's `env` explicitly in YAML).
* Object limits (searched for a comment limit; none stated): https://learn.microsoft.com/en-us/azure/devops/organizations/settings/work/object-limits

State mapping used: normal advisory run `succeeded`; tool failure `error`; baseline missing `notApplicable`; blocking policy hit `failed`.
Assumptions **not** checked against the docs: the authentication header (`basic` personal-access-token, or `bearer`), that the thread `properties` entry
(`cdiPocMarker`, typed as `System.String`, modelled on the typed values shown in the list example) is accepted on create, and how the web UI renders the marker comment.

## Idempotent comment (one thread per PR, updated on every push)
The comment body starts with `<!-- cdi-poc:impact-report:v1 pr=<name> -->` and the thread carries the property `cdiPocMarker`. The Azure adapter lists the PR's threads, ignores deleted
threads and comments, finds the first live comment containing the marker (or a thread with the property) and **updates that comment**; only if none exists it creates a thread.
The status is posted with the same `context.name` every time, which the docs describe as the status identifier. Tests use an in-memory fake of these endpoints (no network).

## Azure DevOps adapter: written, never executed
`ci/adapters.py: AzureDevOpsAdapter` is **disabled unless `--enable-azure-adapter` is passed** (and `--adapter azure`, a pull request id, non-placeholder organization/project/repository values
in the `ci` section of `.cdi/config.yml`, and a token in the environment variable named by `adapter.azure.token_env`). Disabled or misconfigured, it raises before any request is built. The token is read from the
environment only; it is never stored, logged or placed in a URL or body. The real HTTP transport is not even constructed while the adapter is disabled.

## Blocking hook (OFF by default)
`config/ci.yml: blocking.enabled: false`. Turn it on with `blocking.enabled: true` or `--blocking`. When on, a run may fail **only** on a deterministic policy listed in `blocking.policies`:
* `P1-referenced-not-found-introduced` - the PR leaves a procedure/table/view referenced but not defined.
* `P2-route-unmatched-introduced` - a frontend request no longer matches any API route.
Each hit includes file:line, analysis method, commit and reason. It never fails on a risk label, and never on a tool error.
**A deliberate rename or deletion can trigger these**: removing or renaming a procedure, or changing a controller route, is flagged even when the callers are updated in a follow-up PR or
the frontend is deployed together with the API. That is why blocking is off by default and the policies are individually listed; unlisted policies cannot fire.

## config.example/optional/azure/azure-pipelines.yml
Thin wrapper (`backend/scripts/run_pr.sh`), PR trigger, full-depth checkout (three-dot diffs need the merge-base), `continueOnError` so the advisory check never fails the PR, artifacts published from `out/`.
Placeholders only (`<TARGET_BRANCH>`, `<AGENT_POOL>`, `<VARIABLE_GROUP>`, `<ORGANIZATION>`, `<PROJECT>`, `<REPOSITORY_ID>`); no real organization, project, service-connection name or token. The baseline refresh
on merge is a **commented example**. The file parses as YAML (tested) but was never run on an agent.
