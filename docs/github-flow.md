# GitHub flow

Two workflows and one composite action turn the impact engine into a pull-request check on GitHub. **Status (2026-11-11): run on github.com against the sample repository
`promptkernel/cdi-sample-app` ([PR 1](https://github.com/PromptKernel/cdi-sample-app/pull/1), [PR 2](https://github.com/PromptKernel/cdi-sample-app/pull/2), [PR 3](https://github.com/PromptKernel/cdi-sample-app/pull/3)); see "Verified on real GitHub" and
"Not verified" at the end for exactly what that covers.**

| Piece | File |
|---|---|
| Composite action (runs the tool from its pinned ref) | `.github/actions/cdi/action.yml` |
| Workflow 1: build the baseline on the base branch | `config.example/github/workflows/cdi-baseline.yml` |
| Workflow 2: analyse a same-repo pull request | `config.example/github/workflows/cdi-pr.yml` |
| Container image (CLI) | `backend/Dockerfile` (`docker build -t cdi backend`) |
| Code | `backend/src/cdi/github/` (`event`, `client`, `adapter`, `flow`, `summary`, `cli`) |

A target repository copies the two workflows to `.github/workflows/` and adds `.cdi/config.yml` ([configuration](configuration.md)). Both workflows call
`OWNER/cdi-poc/.github/actions/cdi@<FULL_COMMIT_SHA>`; the owner and the 40-character commit are marked `TODO` until a release commit exists.

## Flow
1. **Push to the base branch** (workflow 1): `cdi github baseline` builds the full baseline, writes `baseline.json`, reports its size, and the workflow saves it with
   `actions/cache/save`, key `cdi-baseline-v<schema>-<sha>`. The command refuses any other event or branch.
2. **Pull request** (workflow 2): checkout of the **base** revision, `actions/cache/restore` of the newest baseline, then `cdi github pr`:
   target = the event's base ref; baseline classified against the PR's merge-base; impact analysis; **one** comment (created or updated) and **one** commit status.

## Trust model
| Rule | How it is enforced |
|---|---|
| The baseline is produced only on the base branch | `cdi-baseline.yml` triggers only on `push` to the base branch; `cdi github baseline` also refuses anything else (`GITHUB_EVENT_NAME`/`GITHUB_REF`). Tests: `test_baseline_refuses_any_other_event_or_branch`, `test_baseline_workflow_runs_only_on_push_to_the_base_branch_and_saves`. |
| A PR run never writes or overwrites the baseline | The PR workflow uses `actions/cache/restore` (which cannot save) and the PR flow only calls `GraphStore.read`. Tests: `test_pr_run_comments_sets_status_and_leaves_the_baseline_untouched` (bytes and mtime), `test_pr_flow_cannot_write_any_store` (store writes raise), `test_pr_workflow_reads_the_base_revision_and_only_restores_the_cache`. Per the caching docs, caches a PR run creates are scoped to its merge ref and cannot be restored by the base branch. |
| The target is the PR's base ref, not config | `cdi github pr` takes `pull_request.base.ref` from the event payload; `branches.base` is only the default for local runs. Tests: `test_target_comes_from_the_event_base_ref_not_from_config`, `test_target_defaults_to_branches_base_and_an_explicit_target_overrides_it`. |
| Configuration and tool come from the base, not the PR | `actions/checkout` uses `ref: pull_request.base.sha`; the action runs from its pinned `uses:` ref (`github.action_path`). |
| PR files are data | They are fetched as git objects (`fetch-depth: 0` fetches the same-repo head branch) and parsed by the Roslyn/ts-morph/ScriptDom scanners in a detached git worktree. Nothing from the PR is built, restored, installed or run. `persist-credentials: false` keeps the token off disk. |
| No `pull_request_target` | Not used anywhere (test `test_no_pull_request_target_anywhere`); the secure-use docs warn against it with a PR checkout. |
| Fork PRs | `if: head.repo.full_name == github.repository` in the workflow, and the tool skips them too with a job-summary note (`test_fork_pull_requests_are_skipped_with_a_summary_message`). |
| Third-party actions pinned by commit SHA | Test `test_every_remote_action_is_pinned_by_full_commit_sha` (see "Pinned actions"). |
| No script injection | No attacker-controlled context (titles, branch names, bodies) appears in any expression; action inputs reach scripts only through `env:` (tests). |

### Residual risk (not removed by this design)
* **A same-repository pull request runs the workflow file from its own revision**, so its author can edit `.github/workflows/cdi-pr.yml` (change the
  pin, add steps). Such a job holds a token with exactly the three permissions below and no repository secrets, so the damage is bounded to posting
  comments/statuses and reading the repository, but it is real. (The `pull_request` page I fetched does not state which revision supplies the workflow file;
  treat it as the PR's.)
* Mitigate with **branch protection** on the base branch (required reviews, no direct pushes), a **CODEOWNERS** entry for `.github/` and `.cdi/` so a
  change to workflows or tool configuration needs the owner's review, the organisation setting that makes the default `GITHUB_TOKEN` read-only, and an
  allow-list of actions.
* Anyone who can push to the base branch can change what the baseline workflow builds. Protect that branch.
* The tool executes parsers on untrusted files; a parser bug is a possible attack surface (no sandbox beyond the runner).

## Permissions
Set per workflow; unspecified scopes become `none` once `permissions:` is present.

| Workflow | Permission | Why | Can it be dropped? |
|---|---|---|---|
| baseline | `contents: read` | checkout | no |
| pr | `contents: read` | checkout of the base revision | no |
| pr | `pull-requests: write` | list, create and update the comment (`Issues` or `Pull requests` write; list needs the matching read) | no, unless you only want the status |
| pr | `statuses: write` | create the commit status | **yes** if you only want the comment: the status post then fails as a clear advisory warning (there is no switch to turn the status off yet) |

**Status vs check run.** A check run needs `checks: write`, and the Checks REST page says write access to checks "is only available to GitHub Apps". A
commit status needs `statuses: write` and is documented for callers with push access. Both are one scope; the status is used because it is the simpler,
documented path for a token. `notApplicable` (a skipped run) is reported as `success` because GitHub has only `error`, `failure`, `pending`, `success`; the
description says why.

## Baseline freshness (PR side)
Per logical repo, the baseline's commit id is compared with the repo folder's last commit at the PR's **merge-base**:

| Result | Meaning | What happens |
|---|---|---|
| current | equal | no warning |
| behind | baseline is an ancestor | used; comment says "N commit(s) behind" |
| ahead | baseline is newer than the merge-base (the PR branched earlier) | used; comment flags it (an addition to the three required cases) |
| unmatched | commit unknown or on unrelated history | **full build** of the merge-base in memory, stated in the comment |
| cache missing / schema version mismatch | no file, or `schema_version` differs | same full-build fallback, with the reason; the stored file is never touched |

## Baseline size
After a build, `cdi github baseline` prints the size, puts it in the job summary, and, above `limits.baseline_max_bytes` (default 50 MiB, **placeholder,
unvalidated**), emits a `::warning` annotation and a summary warning. The baseline is still saved. The caching docs give 10 GB per repository and 7-day
eviction of unused entries.

## Advisory failures
A 403, 404 or 422 (or a network error) while posting becomes a message in the job summary and a `::warning` annotation; the run exits 0. Messages say
which permission is missing. A fork PR, a missing token, an unknown base ref or an event without a pull request are summary messages too. Only the
baseline job fails (non-zero) on a tool error, so a broken baseline is visible. Blocking applies only through the deterministic policies in config
(`ci.blocking`), never through GitHub errors.

## Job summary in the log
GitHub has no API to read a job summary, so the tool also prints the summary text into the job log inside `::group::cdi job summary` / `::endgroup::`. The text includes names taken
from pull-request files, so it is printed inert: workflow commands are switched off with `::stop-commands::<random token>` for the duration, and every line is indented. Anything that looks
like a credential (the token, an `Authorization` header, GitHub token patterns) is replaced by `***` before it reaches the summary or the log (tests:
`test_no_token_or_authorization_header_can_appear_in_the_summary_or_the_log`, `test_text_from_pr_files_cannot_act_as_workflow_commands`). The `stop-commands` behaviour is from
GitHub's workflow-command feature and has not been exercised on a real runner yet.

## Comment size
The comment builder already caps at `limits.comment_max_chars` (default 20,000). The adapter additionally truncates to 65,536 characters and the status
description to 140. **Neither number is stated in GitHub's REST pages** (see below); they come from community reports and are treated as conservative caps.

## Pinned actions
Looked up with `gh api` (read-only) on 2026-11-11: each tag resolved to a commit through the tags list, the commits endpoint and the tag ref (all three agree).

| Action | Tag | Commit |
|---|---|---|
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/cache (`/restore`, `/save`) | v6.1.0 | `55cc8345863c7cc4c66a329aec7e433d2d1c52a9` |
| actions/setup-python | v7.1.0 | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` |
| actions/setup-node | v7.1.0 | `949feb2413d6458794dcd2491c4babbbce0c15c1` |
| actions/setup-dotnet | v6.1.0 | `0f4a354dd5547a28c70b7853dbd95d5b67886e73` |

The only unpinned reference is the cdi action itself (`OWNER/cdi-poc/...@<FULL_COMMIT_SHA>`), a marked TODO: there is no release commit to pin yet.

## Sources consulted
* REST, issue comments (create/update/list, status codes 403/404/410/422): https://docs.github.com/en/rest/issues/comments
* REST, commit statuses (states, context, 1000 per sha+context): https://docs.github.com/en/rest/commits/statuses
* REST, check runs ("only available to GitHub Apps"; summary/text 65535): https://docs.github.com/en/rest/checks/runs
* Permissions required: https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps
* Workflow syntax (`permissions`, `concurrency`): https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
* Events (`pull_request`, forks, merge commit): https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
* Contexts (`github.base_ref`): https://docs.github.com/en/actions/reference/workflows-and-actions/contexts
* Workflow commands (job summary 1 MiB, `::warning`): https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands
* Composite actions: https://docs.github.com/en/actions/tutorials/create-actions/create-a-composite-action
* Dependency caching (access restrictions, immutability, eviction, restore keys): https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
* Secure use (SHA pinning, `pull_request_target`, injection, least privilege): https://docs.github.com/en/actions/reference/security/secure-use
* Controlling `GITHUB_TOKEN` permissions: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token

## Verified on real GitHub (2026-11-11, sample repository `promptkernel/cdi-sample-app`)
Run by the tool's author from this repository's `restructure` branch; the sample's workflows pin the tool by full commit SHA (a commit on a branch, no tag needed). Three PRs were used:
[PR 1](https://github.com/PromptKernel/cdi-sample-app/pull/1) (a stored-procedure body), [PR 2](https://github.com/PromptKernel/cdi-sample-app/pull/2) (a renamed route) and
[PR 3](https://github.com/PromptKernel/cdi-sample-app/pull/3) (README only). The sample's pin moved through `39e9383`, `e76ceb2` and `81abdde` and is now `64a288c`; the final runs are
[PR 1](https://github.com/PromptKernel/cdi-sample-app/actions/runs/43044498651), [PR 2](https://github.com/PromptKernel/cdi-sample-app/actions/runs/43044501355),
[PR 3](https://github.com/PromptKernel/cdi-sample-app/actions/runs/43044509236), baseline [43044318693](https://github.com/PromptKernel/cdi-sample-app/actions/runs/43044318693).

| What | Evidence |
|---|---|
| The composite action resolves from a branch commit by SHA and installs on `ubuntu-latest` (Python 3.13, .NET 10, Node 24, `npm ci`, scanner build) | every baseline and PR run; the first baseline run took 33 s |
| Baseline built on push to `main` and saved to the Actions cache | cache keys `cdi-baseline-v1-<sha>`, 13.08 KiB compressed (153,655 bytes of JSON); the same 115 nodes / 125 edges as on macOS |
| A PR run restores the baseline from the base branch's cache (exact key hit) and cannot save | log lines "Cache hit for: cdi-baseline-v1-…", "Cache restored successfully"; the PR workflow has no save step |
| One advisory comment is created, then **updated in place** (same comment id) on every later push; never a duplicate | PR 1 id 6797310661 (five revisions), PR 2 id 6797314921 (four), PR 3 id 6799075229 (two); one bot comment each |
| A commit status `cdi/impact-analysis` is set on every head commit | `gh pr checks`, `commits/<sha>/status` |
| The status description says "Advisory only (status stays success)" first when the label is High (PR 2); the state stays `success` | PR 2 status |
| The results match the local reports for the same edits | the consumer / unresolved / test lines of PR 1 and PR 2 are identical to a local `cdi pr` run |
| PR 1: consumers through the data-access layer, the inferred DI hop, the controller, the UI service and the screen. PR 2: the frontend request is unmatched, the screen is named, risk High | comments |
| A PR that changes only a file no scanner reads (PR 3, `README.md`) gets a short comment: no changed objects, "1 file(s) outside every folder the scanners analyse", no stale warning | PR 3 comment |
| The "based on an OLDER target" warning no longer appears when `main` moved only in files the scanners do not read (the re-pins moved `main` by workflow files only) | PR 1-3 comments after `81abdde`; it did appear before, on `39e9383` |
| The comment's Markdown renders as intended: the attribute-change line is its own paragraph, not a table row; the bold heading after a list is its own paragraph | GitHub's HTML for PR 1 and PR 2 comments |
| The job summary and the full report appear in the job log inside `::group::` markers, inert and without credentials (the runner masks the `stop-commands` token as `***`) | run logs |
| The `pull_request` run uses the workflow file of the merge result: after `main` re-pinned the action, PR runs used the new version although the PR branches still carried the old file | PR runs after each re-pin |
| Runtime: job 29-37 s, the analysis step 22-27 s, tool run 3-5 s (small sample) | step timings |

### Defects found by the real runs, and their fixes
1. The Basis line showed `origin/main` and the head sha twice; the footer pointed at `out/report-<pr>.md` on the runner; the footer called the repository "synthetic-scale". Fixed in `e76ceb2` (verified on the second real run).
2. The full report named `origin/main` and the head sha and said "Baseline graph (Neo4j, read-only)" for a JSON baseline. Fixed in `9837aab`/`81abdde` (verified on the third round of runs).
3. The "older target" warning appeared whenever `main` had moved, even by a workflow file. Fixed in `499b703`: it needs a changed file that matches a repo's include/exclude globs or `.cdi/`; the **negative** case is verified on GitHub, the positive case (a scanned file moved) only in tests.
4. A fixed claim "measured on this small synthetic sample" in reports and the explorer banner; now driven by the synthetic flag (`23ff458`). Reports and the banner were verified in the run logs; the evaluation harness wording only in tests.
5. A High risk label next to a green status looked contradictory: the description now starts "Advisory only (status stays success)" (`81abdde`).
6. Markdown: a line under the table became a table row, and a bold heading under a list was swallowed by the list; an empty "Inferred consumers (0)" block was announced (`81abdde`).
7. A README-only PR said "Changed files: 0". Fixed in `64a288c`.
8. The tool left a `cdi-scanner-config-*` directory in the temp folder on every run (234 had accumulated). Fixed in `ba4a55f`; tested locally (normal exit, failure, SIGTERM). On the runner it was not observable.

## Not verified
* **Fork pull requests** (this needs a second account): the skip is tested only against the fake server.
* **Real 403, 404 and 422 responses.** The declared permissions worked, so no error path ran. The adapter's messages are tested against the fake server only; GitHub's actual error bodies are unseen.
* **Baseline fallbacks on GitHub:** a cache miss, a schema-version mismatch, an unmatched or "behind" baseline, and the `limits.max_changed_files` skip were exercised against the fake server and local git only. The run on GitHub always had a current baseline.
* **The baseline size warning** and anything near the 10 GB cache limit or 7-day eviction: the real baseline is 150 KB.
* **Larger repositories**: timing and memory beyond the small sample.
* **GitHub's own limits**: the 65,536-character comment cap and the 140-character status description cap are still community-reported, not seen in the official REST pages; the real comments were far below them.
* **Check runs** (not used); GitHub Enterprise Server; Ubuntu 26 (the runner image notice says `ubuntu-latest` migrates from 2026-10-19).
* The Docker image on CI.
