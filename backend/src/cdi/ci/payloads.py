"""Azure DevOps request bodies for a PR thread, a thread-comment update and a PR status.
SHAPES FOLLOW THE PUBLIC REST DOCS (api-version 7.1; URLs in docs/ci-simulation.md) AND HAVE NOT BEEN TESTED AGAINST A REAL SERVICE."""
from __future__ import annotations

# GitStatusState enumeration from the docs
STATES = ("notSet", "pending", "succeeded", "failed", "error", "notApplicable")


def marker_text(marker, pr_name):
    return f"<!-- {marker}:v1 pr={pr_name} -->"


def thread_payload(content, marker, thread_status="active"):
    """POST .../pullRequests/{id}/threads  (Pull Request Threads - Create). The marker is in the content AND in a thread property."""
    return {"comments": [{"parentCommentId": 0, "content": content, "commentType": "text"}],
            "status": thread_status,
            "properties": {"cdiPocMarker": {"$type": "System.String", "$value": marker}}}


def comment_update_payload(content):
    """PATCH .../threads/{threadId}/comments/{commentId}  (Pull Request Thread Comments - Update)."""
    return {"content": content}


def status_payload(state, description, context, max_description=300, target_url=None):
    """POST .../pullRequests/{id}/statuses  (Pull Request Statuses - Create). context.name is the only required field and identifies the status."""
    if state not in STATES:
        raise ValueError(f"state {state!r} is not a GitStatusState value {STATES}")
    d = description if len(description) <= max_description else description[: max_description - 1] + "…"
    body = {"state": state, "description": d, "context": {"name": context["name"], "genre": context.get("genre", "")}}
    if target_url:
        body["targetUrl"] = target_url
    return body
