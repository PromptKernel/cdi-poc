"""Post the impact report to a GitHub pull request: ONE comment (found by a hidden marker, created or updated) and ONE commit status.

Why a commit status and not a check run: the REST docs say that writing checks "is only available to GitHub Apps" and needs `checks: write`;
a commit status needs only `statuses: write` and is documented for any caller with push access. Comments need `pull-requests: write`
(or `issues: write`); reading existing comments needs the matching read scope. See docs/github-flow.md for the URLs.

Failures never raise: a 403/404/422 or a network error becomes an entry in result["errors"] with an actionable message, and the run stays advisory."""
from __future__ import annotations
import re
from cdi.ci import payloads
from cdi.ci.adapters import PostingAdapter
from .client import Client, GitHubError

# UNVERIFIED limits: GitHub's REST pages state neither (see docs/github-flow.md). They come from community reports (comment body "maximum is 65536
# characters", commit status description 140 characters); we truncate to them so that a too-long value cannot cause a 422.
COMMENT_HARD_CAP = 65536
STATUS_DESCRIPTION_CAP = 140

STATE_MAP = {"succeeded": "success", "failed": "failure", "error": "error", "pending": "pending", "notSet": "pending",
             # GitHub has no "not applicable": a skipped (advisory) run is reported as success with the reason in the description
             "notApplicable": "success"}


def truncate(text: str, cap: int, note="\n\n_Comment truncated to fit GitHub's size limit; see the job summary or the uploaded report._\n"):
    if len(text) <= cap:
        return text, False
    keep = text[: cap - len(note)]
    return keep + note, True


def explain(err: GitHubError, what: str, need: str) -> str:
    if err.status == 403:
        return (f"{what}: HTTP 403 Forbidden. The workflow token lacks `{need}` or the run is not allowed to write "
                f"(pull requests from forks get a read-only token). GitHub said: {err.message}")
    if err.status == 404:
        return (f"{what}: HTTP 404 Not Found. The repository, pull request or commit is not visible to this token, or the token has no access "
                f"(needs `{need}`). GitHub said: {err.message}")
    if err.status == 422:
        return f"{what}: HTTP 422 Validation failed. GitHub said: {err.message}"
    if err.status == 0:
        return f"{what}: {err.message}"
    return f"{what}: HTTP {err.status}. GitHub said: {err.message}"


class GitHubAdapter(PostingAdapter):
    def __init__(self, client: Client, repo: str, pr_number: int, head_sha: str, author="github-actions[bot]", target_url=None):
        self.client, self.repo, self.pr, self.sha, self.author, self.target_url = client, repo, pr_number, head_sha, author, target_url

    def _find_own_comment(self, marker):
        needle = f"<!-- {marker}:v1"
        comments = self.client.get_all(f"/repos/{self.repo}/issues/{self.pr}/comments")
        # Only comments written by the workflow's own identity count: another user pasting the marker must not make us edit their comment.
        mine = [c for c in comments if needle in (c.get("body") or "") and (c.get("user") or {}).get("login") == self.author]
        return sorted(mine, key=lambda c: c["id"])

    def post(self, pr_name, comment_md, status, marker):
        res = {"adapter": "github", "repo": self.repo, "pr": self.pr, "comment": None, "status": None, "errors": [], "truncated": False}
        body, res["truncated"] = truncate(comment_md, COMMENT_HARD_CAP)
        try:
            mine = self._find_own_comment(marker)
            if len(mine) > 1:
                res["duplicates_left_untouched"] = [c["id"] for c in mine[1:]]
            if mine:
                c = mine[0]
                if c.get("body") == body:
                    res["comment"] = {"action": "unchanged", "id": c["id"], "url": c.get("html_url")}
                else:
                    _, c = self.client.request("PATCH", f"/repos/{self.repo}/issues/comments/{c['id']}", {"body": body})
                    res["comment"] = {"action": "updated", "id": c["id"], "url": c.get("html_url")}
            else:
                _, c = self.client.request("POST", f"/repos/{self.repo}/issues/{self.pr}/comments", {"body": body})
                res["comment"] = {"action": "created", "id": c["id"], "url": c.get("html_url")}
        except GitHubError as e:
            res["errors"].append(explain(e, "comment", "pull-requests: write (or issues: write)"))
        try:
            gh_state = STATE_MAP[status["state"]]
            desc = status["description"]
            desc = desc if len(desc) <= STATUS_DESCRIPTION_CAP else desc[: STATUS_DESCRIPTION_CAP - 1] + "…"
            payload = {"state": gh_state, "description": desc, "context": status["context"]["name"]}
            if self.target_url:
                payload["target_url"] = self.target_url
            self.client.request("POST", f"/repos/{self.repo}/statuses/{self.sha}", payload)
            res["status"] = {"state": gh_state, "context": payload["context"]}
        except GitHubError as e:
            res["errors"].append(explain(e, "commit status", "statuses: write"))
        return res
