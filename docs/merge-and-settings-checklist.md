# Merge status and repository settings (state on 2026-11-12, after the merge and the re-pins)

## What has been done
* `restructure` was fast-forwarded into `main` of `PromptKernel/cdi-poc`; `restructure` still exists (do not delete it without a decision). The six explorer screenshots are in history (`c32e7e5`, reviewed and approved as clean) but not in any tree.
* `promptkernel/cdi-sample-app` pins the tool at a commit on `main` (see below). Nothing in GitHub's settings was changed by the tool's author.

## Allow-list entries you must set yourself (full SHAs, exactly what the workflows use)
Apply to **`promptkernel/cdi-sample-app`** (*Settings > Actions > General > Actions permissions > "Allow select actions and reusable workflows"*, plus "Require actions to be pinned to a full-length commit SHA"):
```
actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1            # v7.0.1
actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9      # v6.1.0
actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9         # v6.1.0
promptkernel/cdi-poc/.github/actions/cdi@2476a3a2b39e0db40aaa9afed080b07ec1c986f3  # pinned by the sample as of 2026-11-12 (replaces the earlier b42bae8 and 5eb4ef9 entries)
```
and, because the composite action calls them, these three as well (they are pinned inside `.github/actions/cdi/action.yml` of the tool at that commit):
```
actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0       # v7.1.0
actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1         # v7.1.0
actions/setup-dotnet@0f4a354dd5547a28c70b7853dbd95d5b67886e73       # v6.1.0
```
The tool entry **changes at every re-pin**: update it (and the sample's two workflow files) together. For **`PromptKernel/cdi-poc`** itself there are no workflows yet, so no entries are needed until a CI workflow is added.

## Settings checklist: current state (read-only API calls, both repositories) and what you apply
| Setting | State now | You apply |
|---|---|---|
| Protect `main` (PR required, 1+ approval, dismiss stale approvals, Code Owner review, required check `cdi/impact-analysis` on the sample, no force-push, no deletion, linear history, include administrators) | `main` **not protected** on both | yes |
| CODEOWNERS (`/.github/` and `/.cdi/` -> owner or team), in `.github/CODEOWNERS` on `main` | **absent** on both | yes |
| Default workflow token read-only; "create and approve pull requests" off | **already** `read` / `false` on both | keep |
| Actions allow-list + require full-SHA pinning | allowed actions = **all**; SHA pinning **not** required, both | yes (entries above) |
| Fork pull request workflows: require approval for outside contributors | not checked (no API call made) | yes |
| Secret scanning and push protection | **enabled / enabled** on both | keep |
| Repository secrets | none used | keep none |

## Merge facts
* Tool `main` = the merge tip plus later commits (see the final report); the pre-merge checklist and the fast-forward commands that were used:
  ```
  gh auth status; git fetch origin; git switch main
  git merge --ff-only origin/restructure
  scripts/prepush_gate.sh && git push origin main
  ```
* To re-pin the sample after any tool change: edit the 40-character SHA after `.github/actions/cdi@` in `cdi-baseline.yml` and `cdi-pr.yml`, `git add -- <those two files>`, `scripts/prepush_gate.sh && git push origin main` from the sample repository, wait for the baseline run and its cache key `cdi-baseline-v1-<sha>`, push an empty commit to each open demo branch, and check each PR still has one bot comment (same id) that was updated.
