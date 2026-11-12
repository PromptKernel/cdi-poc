# Pre-push gate and pre-commit hook

Nothing is pushed until a script that can **fail** has looked at it. The gate is `scripts/prepush_gate.sh`; the hook is `.githooks/pre-commit`.

## Every push is one command
```
scripts/prepush_gate.sh && git push -u origin <branch>
```
Joined with `&&`, so a failing gate stops the push. **Never** chain them with `;` or `&`, and never run the gate for information and then push in a separate step: a printed warning does not stop anything.
The same applies to `gh` commands that publish content.

## What the gate checks (any hit exits non-zero and every hit is printed in full)
| Check | Looks at |
|---|---|
| `images` | tracked or staged image files (`IMAGE_EXTENSIONS`, default png jpg jpeg gif webp) outside `ALLOW_IMAGE_DIRS` (default: nowhere), and any image **added by a commit about to be pushed**, even if a later commit deletes it |
| `paths` | tracked, staged or newly added paths under `FORBIDDEN_PATHS` |
| `names` | each regex of `TERMS_FILE` against the committed tree, the added lines of the commits to be pushed, commit messages and author fields. A missing terms file **fails** the gate |
| `paths` (local) | home-directory paths (`/Users/<x>`, `/home/<x>`, `C:\Users\<x>`), plus this machine's own `$HOME` and login name |
| `credentials` | token and key patterns, and **gitleaks** over the commits to be pushed and over staged changes (a missing gitleaks fails the gate) |
| `authors` | every author and committer email must match `ALLOWED_EMAIL_REGEX` (default: exactly `git config user.email`) |
| `overlap` | optional: no run of `OVERLAP_WORDS` words shared with a private text (`OVERLAP_FILE`); when the file is absent the gate says the check was not run |

"Commits to be pushed" = every commit not yet on the remote of the branch's upstream (`HEAD --not --remotes=<remote>`), or every commit on no remote when there is no upstream; override with `--range`.
So merging a branch that is already pushed (e.g. fast-forwarding `main` to `origin/restructure`) does not re-scan commits that are public already; the committed tree and the staging area are still scanned in full,
and any new commit is scanned in full. The gate prints how many commits it skipped for that reason.

## The default range: commits not yet on the remote
**Rule.** Unless `--range` is given, the gate checks the commits that are not yet on the remote of the branch's upstream: `HEAD --not --remotes=<remote>`. With no upstream it checks every commit that is on no remote. The committed tree and the staging area are always scanned in full, and every new commit is scanned in full (files, added lines, messages, authors). The gate prints how many commits it skipped because they are already on the remote.

**Why.** The first version scanned everything reachable from `HEAD`. Fast-forwarding `main` to an already pushed branch then re-flagged content that was public already (six images from an earlier commit, two fake credential-looking test strings), so a push of nothing new was blocked and the only ways forward were to disable the gate or to rewrite public history. Rewriting history was ruled out, and a gate that has to be bypassed is worse than none. Checking what a push would *publish* is the purpose of the gate; what the remote already holds cannot be un-published by it. Commits that are already public stay visible in history; the gate does not claim to clean them.

**What this does not do.** It does not scan commits on the remote, so anything already public is not re-checked; it does not weaken the tree scan, so a bad file still tracked at the tip is always caught.

**The push form (exactly one command, no pipe, no `tail`, no `;`):**
```
scripts/prepush_gate.sh && git push origin <branch>
```
`&&` makes the push run only if the gate exits 0. Do not put a pipe in the gate's command (`scripts/prepush_gate.sh | tail -1 && git push ...`): a pipeline takes the exit status of its last command, so a failing gate would not stop the push and the output would be filtered. Do not use `;` or `&` either. Read the complete gate output; it is the check.

## Nothing is hardcoded
Rules live in `.prepush-gate.conf` (`KEY=value`, parsed and never executed) and in `PREPUSH_<KEY>` environment variables, which win. The file holds no names, paths or identities.
The private names to search for go in `private/prepush-terms.txt` (one regex per line) and the private text for the overlap check in `private/overlap-source.txt`; `private/` is git-ignored.
The gate works in any repository: `../cdi-poc/scripts/prepush_gate.sh --conf <rules file>` from another checkout.

## The hook
`git config core.hooksPath .githooks` (once per clone). `.githooks/pre-commit` rejects staged image files and staged `FORBIDDEN_PATHS` with the offending path and the command to unstage it.

## Staging rule
Stage with explicit file paths only: `git add -- path/to/file`. Never `git add .`, `git add -A` or `git add <directory>`: that is how images that were meant to stay untracked got committed once.
After `git add`, look at the **complete** `git status --short` and `git diff --cached --stat` before committing; do not filter them.

## Limits
The gate cannot know a name it was not told; it does not read binary files; it does not inspect what a remote already holds. Tests: `backend/tests/test_prepush_gate.py` (temporary repositories).
