# GitHub flow

Two workflows and one composite action turn the impact engine into a pull-request check on GitHub. **Status: written and tested against an in-memory fake
GitHub server; not yet run on github.com.** The real run is Phase 7 (see "Verified and not verified").

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

## Verified and not verified
**Verified against the docs above:** endpoint paths and methods; the permissions the comment and status endpoints need; the 403/404/422 codes for comments;
the status states; `github.base_ref`; fork PRs get a read-only token and no secrets; the job-summary size limit; composite-action syntax; cache access, scope
and immutability rules; SHA pinning advice.

**Not stated by the official pages (used as conservative assumptions):** the comment body maximum (65,536 characters: community reports only); the commit
status description maximum (140: community reports only; the statuses page gives no limit); that `GITHUB_TOKEN` may call the checks API (the page says apps only).

**Not verified at all:** anything on github.com. The fake server in `backend/tests/fake_github.py` implements my reading of the docs, so tests prove the
tool matches that reading, not that GitHub behaves like it. Unchecked in particular: the exact 403/404/422 response bodies; whether `actions/cache/restore`
finds a baseline saved by the push workflow across the exact key/prefix rules in practice; runner timing and memory. The Docker image was built and run locally (`cdi github baseline` on a clone of the sample repository gave the same baseline as the host
run), but not on CI, and base images are referenced by tag, not digest. The cdi action has not been executed by a runner. Phase 7 does the first real run.
