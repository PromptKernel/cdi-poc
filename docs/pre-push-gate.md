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
