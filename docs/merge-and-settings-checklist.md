# Merge preparation and repository settings (commands are prepared, NOT run)

## Facts as of 2026-11-11 (read-only checks)
* `PromptKernel/cdi-poc`: `main` = `2e44f06`; branch `restructure` is 43 commits ahead of it and a **fast-forward** of it. Local `main` (`42ff3ee`) is also an ancestor of `restructure`.
* The six explorer screenshots were pushed by mistake in `c32e7e5` and removed from the tree in `56caa05`. **They remain in the history**; after a fast-forward merge they are in `main`'s history too (reviewed and approved as clean).
* `promptkernel/cdi-sample-app`: `main` = `c0c9f1d`; both workflows pin the tool at `64a288c` (full SHA). `64a288c` is reachable on GitHub only through the branch `restructure` until the merge.
* GitHub settings found: both repositories have default workflow token = read, "approve pull requests" = off, allowed actions = **all**, SHA pinning **not** required, `main` **not** protected, no CODEOWNERS file, secret scanning enabled.

## Pre-merge checklist
1. All local commits that should ship are pushed through the gate (`scripts/prepush_gate.sh && git push origin restructure`); the commit `7c09946` (temp-directory registry fix) is currently local only.
2. `scripts/prepush_gate.sh` passes; `backend` suite green with no Neo4j (439 passed + the new test); `cdi audit` 0 hits; the frontend suites pass.
3. The three demo PRs still behave (comment updated in place, status set); the README banner says what is true after the merge (it currently says "not merged to `main`": change it in a commit before merging).
4. **Do not delete `restructure`** before the sample repository is re-pinned (below): until the merge, the pinned commit exists only through that branch. After the merge, keep it until the re-pin is verified.
5. You have decided about the six PNGs in history (this checklist assumes: leave them).

## Merge commands (fast-forward only)
```
cd /path/to/cdi-poc
gh auth status                                  # the active account must be PromptKernel
git fetch origin
git switch main
git merge --ff-only origin/restructure          # refuses unless it is a pure fast-forward
scripts/prepush_gate.sh && git push origin main # ONE command; fast-forwards 2e44f06 -> the restructure tip
gh api repos/PromptKernel/cdi-poc/branches/main --jq .commit.sha   # must equal the tip you merged
```
Not `--no-ff`, not `--force`, no tags, `restructure` stays.

## Re-pin the sample workflows (after the merge)
The current pin `64a288c` is an ancestor of the new `main`, so it stays reachable and valid after a fast-forward merge. Re-pin anyway to a commit that is on `main` (the merge tip, or a tag you create on `main`),
so the pin no longer depends on a feature branch and picks up later fixes (for example `7c09946`):
1. In `cdi-sample-app`: replace the 40-character SHA after `.github/actions/cdi@` in `.github/workflows/cdi-baseline.yml` and `cdi-pr.yml`; commit with explicit `git add -- <file>` paths.
2. `scripts/prepush_gate.sh && git push origin main` from that repository (the gate works in any repo: `<path>/cdi-poc/scripts/prepush_gate.sh --conf <rules>`).
3. Wait for the baseline run and its cache key `cdi-baseline-v1-<sha>`; push an empty commit to each open demo branch; check each PR's single comment was updated in place.
4. Only then consider deleting `restructure` (needs your approval).

## Repository settings you must apply yourself (I changed nothing)
Apply to `PromptKernel/cdi-poc` and `promptkernel/cdi-sample-app`. Settings are under *Settings*.
- [ ] **Branch protection or a ruleset for `main`** (*Branches* / *Rules*): require a pull request; at least 1 approval; dismiss stale approvals on new commits; **require review from Code Owners**; require status checks
      (sample repository: `cdi/impact-analysis`; tool repository: add a CI check first, there is none yet); block force pushes; block deletion; require linear history (keeps merges fast-forward); include administrators.
- [ ] **CODEOWNERS** (`.github/CODEOWNERS` on `main`), so a change to workflows or tool configuration needs the owner's review:
      ```
      /.github/   @<owner-or-team>
      /.cdi/      @<owner-or-team>
      ```
      (a pull request can edit its own workflow file; this plus "require review from Code Owners" is the mitigation named in `docs/github-flow.md`).
- [ ] **Default workflow token = read-only** (*Actions > General > Workflow permissions*: "Read repository contents and packages permissions"). Already the case today; keep "Allow GitHub Actions to create and approve pull requests" **off**.
- [ ] **Actions allow-list** (*Actions > General > Actions permissions*): "Allow select actions and reusable workflows", and tick **"Require actions to be pinned to a full-length commit SHA"** (currently off). Allowed patterns for the sample repository:
      `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`, `actions/cache/*@55cc8345863c7cc4c66a329aec7e433d2d1c52a9`, `actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`,
      `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1`, `actions/setup-dotnet@0f4a354dd5547a28c70b7853dbd95d5b67886e73`, and the tool: `promptkernel/cdi-poc/.github/actions/cdi@<pinned SHA>`
      (update the last entry on every re-pin).
- [ ] **Fork pull requests** (*Actions > General > Fork pull request workflows*): require approval for all outside contributors. The workflows skip fork PRs anyway.
- [ ] **Secret scanning and push protection**: secret scanning and push protection are both enabled on `cdi-poc` today (read-only check); confirm the same for the sample repository.
- [ ] No repository or organisation **secrets** are needed by these workflows; keep it that way.
