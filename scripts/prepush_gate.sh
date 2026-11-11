#!/usr/bin/env bash
# Pre-push gate. Exits NON-ZERO if any check hits, and prints every hit in full: nothing is filtered or hidden.
#
#   scripts/prepush_gate.sh && git push origin <branch>      # ALWAYS one command joined with &&, never ';' or '&'
#
# usage: scripts/prepush_gate.sh [--range <rev-range>] [--conf <file>]
#   --range   commits that would be pushed (default: @{upstream}..HEAD, else every commit that is on no remote: HEAD --not --remotes)
#   --conf    rules file (default: $PREPUSH_CONFIG, else <repo>/.prepush-gate.conf if it exists)
# Nothing here is specific to one repository or person. Rules come from the rules file (KEY=value lines, parsed and never executed) and from the
# environment (PREPUSH_<KEY> overrides the file):
#   IMAGE_EXTENSIONS     image types that must not be tracked or pushed            (default: png jpg jpeg gif webp)
#   ALLOW_IMAGE_DIRS     folders where images may be tracked, space separated      (default: none)
#   FORBIDDEN_PATHS      path prefixes that must not be tracked or pushed          (default: none)
#   ALLOWED_EMAIL_REGEX  regex every author and committer email must match         (default: exactly the current `git config user.email`)
#   TERMS_FILE           one private-name regex per line; keep the file git-ignored. A missing file FAILS the gate (PREPUSH_ALLOW_MISSING_TERMS=1 to skip, visibly)
#   OVERLAP_FILE         optional private text: added lines must share no run of OVERLAP_WORDS (default 5) words with it; skipped, visibly, when absent
#   PREPUSH_ALLOW_NO_GITLEAKS=1   run without gitleaks (the skipped check is still reported)
set -u

RANGE=""; CONF="${PREPUSH_CONFIG:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --range) RANGE="$2"; shift 2 ;;
    --conf)  CONF="$2"; shift 2 ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
TOP="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "GATE FAIL [repo]: not inside a git repository" >&2; exit 2; }
cd "$TOP" || exit 2
if [ -z "$CONF" ] && [ -f ".prepush-gate.conf" ]; then CONF=".prepush-gate.conf"; fi

# ---- rules: defaults, then the rules file, then PREPUSH_<KEY> variables
IMAGE_EXTENSIONS="png jpg jpeg gif webp"; ALLOW_IMAGE_DIRS=""; FORBIDDEN_PATHS=""; ALLOWED_EMAIL_REGEX=""; TERMS_FILE=""; OVERLAP_FILE=""; OVERLAP_WORDS=5
if [ -n "$CONF" ]; then
  [ -f "$CONF" ] || { echo "GATE FAIL [config]: rules file not found: $CONF"; exit 1; }
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    key="${line%%=*}"; val="${line#*=}"; val="${val%\"}"; val="${val#\"}"
    case "$key" in
      IMAGE_EXTENSIONS|ALLOW_IMAGE_DIRS|FORBIDDEN_PATHS|ALLOWED_EMAIL_REGEX|TERMS_FILE|OVERLAP_FILE|OVERLAP_WORDS) printf -v "$key" '%s' "$val" ;;
      *) echo "GATE FAIL [config]: unknown key '$key' in $CONF"; exit 1 ;;
    esac
  done < "$CONF"
fi
for k in IMAGE_EXTENSIONS ALLOW_IMAGE_DIRS FORBIDDEN_PATHS ALLOWED_EMAIL_REGEX TERMS_FILE OVERLAP_FILE OVERLAP_WORDS; do
  ev="PREPUSH_$k"; if [ -n "${!ev+x}" ]; then printf -v "$k" '%s' "${!ev}"; fi
done
esc() { printf '%s' "$1" | sed 's/[][\.*^$+?(){}|\\/]/\\&/g'; }
if [ -z "$ALLOWED_EMAIL_REGEX" ]; then ALLOWED_EMAIL_REGEX="^$(esc "$(git config user.email)")\$"; fi
if [ -z "$RANGE" ]; then
  if git rev-parse --verify -q '@{upstream}' >/dev/null; then RANGE="@{upstream}..HEAD"; else RANGE="HEAD --not --remotes"; fi
fi

FAILS=0; SUMMARY=""
mark() { case "$SUMMARY" in *"[$1]"*) ;; *) SUMMARY="$SUMMARY [$1]" ;; esac; }
report() {   # report <check> <what> <multi-line text>: one GATE FAIL line per line of text
  local check="$1" what="$2" text="$3" line
  [ -z "$text" ] && return 0
  while IFS= read -r line; do printf 'GATE FAIL [%s]: %s: %s\n' "$check" "$what" "$line"; FAILS=$((FAILS+1)); done <<< "$text"
  mark "$check"
}
fail1() { printf 'GATE FAIL [%s]: %s\n' "$1" "$2"; FAILS=$((FAILS+1)); mark "$1"; }
note()  { printf 'gate note [%s]: %s\n' "$1" "$2"; }

echo "== pre-push gate: $TOP"
echo "== commits to be pushed: $(git rev-list $RANGE | wc -l | tr -d ' ')   range: $RANGE"
echo "== rules: ${CONF:-none}; images: $IMAGE_EXTENSIONS (allowed in: ${ALLOW_IMAGE_DIRS:-nowhere}); forbidden paths: ${FORBIDDEN_PATHS:-none}"

# Everything that is tracked or staged now, plus every path ADDED by a commit to be pushed (an image added and deleted inside the range is still pushed).
ALL_FILES="$( { git ls-files; git log --diff-filter=A --name-only --format= $RANGE; } | sort -u )"
ADDED="$( { git log -p --format= $RANGE; git diff --cached; } | grep -E '^\+')"   # added lines of the commits to be pushed and of staged changes, including the '+++ path' headers (a path can carry a name too)
MESSAGES="$(git log --format='%H %an <%ae> %cn <%ce>%n%B' $RANGE)"

# ---- 1. images
imgs=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  lf="$(printf '%s' "$f" | tr '[:upper:]' '[:lower:]')"; is_img=0
  for e in $IMAGE_EXTENSIONS; do case "$lf" in *."$e") is_img=1 ;; esac; done
  [ $is_img -eq 0 ] && continue
  ok=0; for d in $ALLOW_IMAGE_DIRS; do case "$f" in "$d"/*) ok=1 ;; esac; done
  [ $ok -eq 0 ] && imgs="$imgs$f"$'\n'
done <<< "$ALL_FILES"
report images "image file tracked, staged or in the commits to be pushed" "${imgs%$'\n'}"

# ---- 2. forbidden paths
for p in $FORBIDDEN_PATHS; do
  m=""; while IFS= read -r f; do case "$f" in "$p"*) m="$m$f"$'\n' ;; esac; done <<< "$ALL_FILES"
  report paths "forbidden path ($p)" "${m%$'\n'}"
done

# ---- scanning helper: the committed tree, the added lines of the commits to be pushed, and messages/author fields
scan() {   # scan <check> <what> <regex> [i]
  local check="$1" what="$2" re="$3" ic="${4:-}" fl="-nIE"; [ -n "$ic" ] && fl="-nIiE"
  report "$check" "$what in the committed tree" "$(git grep $fl -e "$re" HEAD 2>/dev/null)"
  report "$check" "$what in the staging area" "$(git grep $fl -e "$re" --cached 2>/dev/null)"
  report "$check" "$what in an added line of the commits to be pushed" "$(printf '%s\n' "$ADDED" | grep ${ic:+-i} -nE -e "$re")"
  report "$check" "$what in a commit message or author field" "$(printf '%s\n' "$MESSAGES" | grep ${ic:+-i} -nE -e "$re")"
}

# ---- 3. private names (regexes from a private, git-ignored file)
if [ -z "$TERMS_FILE" ] || [ ! -f "$TERMS_FILE" ]; then
  if [ "${PREPUSH_ALLOW_MISSING_TERMS:-0}" = "1" ]; then note names "no terms file: the private-name search was NOT run"
  else fail1 names "no private-terms file (TERMS_FILE='$TERMS_FILE'): create one (a regex per line, git-ignored) or set PREPUSH_ALLOW_MISSING_TERMS=1"; fi
else
  while IFS= read -r term || [ -n "$term" ]; do
    case "$term" in ''|'#'*) continue ;; esac
    scan names "private name matching a term from $TERMS_FILE" "$term" i
  done < "$TERMS_FILE"
fi

# ---- 4. local paths: generic home-directory shapes, and this machine's own home directory and login name
scan paths "home-directory path" '((^|[^A-Za-z0-9._~/-])/(Users|home)/[A-Za-z0-9._-]+|[A-Za-z]:\\Users\\[A-Za-z0-9._-]+)'    # not './home/x' or 'app/home/x'
for own in "${HOME:-}" "$(id -un 2>/dev/null)"; do
  if [ "${#own}" -ge 4 ] && [ "$own" != "/" ]; then scan paths "this machine's own path or login name" "$(esc "$own")"; fi
done

# ---- 5. credentials
scan credentials "token or key pattern" '(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|[Aa]uthorization: *(Bearer|token|Basic) +[A-Za-z0-9._~+/=-]{12,})'
if command -v gitleaks >/dev/null 2>&1; then
  out="$(gitleaks detect --source . --no-banner --redact --log-opts="$RANGE" 2>&1)"; rc=$?
  if [ $rc -ne 0 ]; then printf '%s\n' "$out"; fail1 gitleaks "gitleaks found something in the commits to be pushed (exit $rc)"; else printf 'gitleaks (commits to be pushed): %s\n' "$out"; fi
  if ! git diff --cached --quiet; then      # staged but not yet committed content
    out="$(gitleaks protect --staged --no-banner --redact 2>&1)"; rc=$?
    if [ $rc -ne 0 ]; then printf '%s\n' "$out"; fail1 gitleaks "gitleaks found something in the staged changes (exit $rc)"; else printf 'gitleaks (staged): %s\n' "$out"; fi
  fi
elif [ "${PREPUSH_ALLOW_NO_GITLEAKS:-0}" = "1" ]; then note gitleaks "gitleaks is not installed: that check was NOT run"
else fail1 gitleaks "gitleaks is not installed (set PREPUSH_ALLOW_NO_GITLEAKS=1 to run without it)"; fi

# ---- 6. author and committer emails
bad=""
while IFS=' ' read -r sha ae ce; do
  [ -z "$sha" ] && continue
  [[ "$ae" =~ $ALLOWED_EMAIL_REGEX ]] || bad="$bad$sha author <$ae> does not match $ALLOWED_EMAIL_REGEX"$'\n'
  [[ "$ce" =~ $ALLOWED_EMAIL_REGEX ]] || bad="$bad$sha committer <$ce> does not match $ALLOWED_EMAIL_REGEX"$'\n'
done < <(git log --format='%h %ae %ce' $RANGE)
report authors "unexpected identity" "${bad%$'\n'}"

# ---- 7. overlap with a private text (optional)
if [ -n "$OVERLAP_FILE" ] && [ -f "$OVERLAP_FILE" ]; then
  ov="$(printf '%s\n' "$ADDED" | python3 -c '
import re, sys
n = int(sys.argv[2]); norm = lambda t: re.findall(r"[a-z0-9]+", t.lower())
src = norm(open(sys.argv[1], errors="ignore").read()); grams = {tuple(src[i:i+n]) for i in range(len(src) - n + 1)}
for i, line in enumerate(sys.stdin, 1):
    w = norm(line)
    for j in range(len(w) - n + 1):
        if tuple(w[j:j+n]) in grams:
            print("added line %d shares %d words with the private text: %s" % (i, n, " ".join(w[j:j+n]))); break
' "$OVERLAP_FILE" "$OVERLAP_WORDS")"
  report overlap "overlap" "$ov"
else
  note overlap "no overlap source (OVERLAP_FILE='${OVERLAP_FILE}'): the overlap check was NOT run"
fi

echo
if [ "$FAILS" -gt 0 ]; then echo "GATE FAILED: $FAILS hit(s) in:$SUMMARY"; exit 1; fi
echo "GATE PASSED"; exit 0
