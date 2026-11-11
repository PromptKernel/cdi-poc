"""Read the webhook payload GitHub gives the runner (GITHUB_EVENT_PATH) and extract what a PR run needs.
The target branch comes from the PR's base ref in this payload, never from configuration."""
from __future__ import annotations
import dataclasses, json, os, pathlib


class EventError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class PullRequestEvent:
    number: int
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    base_repo: str
    head_repo: str | None        # None when the fork was deleted
    action: str

    @property
    def is_fork(self) -> bool:
        return self.head_repo is None or self.head_repo.lower() != self.base_repo.lower()


def load_event(environ=None):
    env = os.environ if environ is None else environ
    path = env.get("GITHUB_EVENT_PATH")
    if not path:
        return None
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise EventError(f"cannot read the event payload {path}: {e}") from e


def parse_pull_request(event) -> PullRequestEvent:
    pr = (event or {}).get("pull_request")
    if not pr:
        raise EventError("the event payload has no pull_request object (this flow runs on pull_request events)")
    try:
        base, head = pr["base"], pr["head"]
        if not base.get("ref"):
            raise EventError("the pull_request payload has no base ref")
        return PullRequestEvent(number=int(pr["number"]), base_ref=base["ref"], base_sha=base["sha"], head_ref=head["ref"], head_sha=head["sha"],
                                base_repo=base["repo"]["full_name"], head_repo=(head.get("repo") or {}).get("full_name"), action=event.get("action", ""))
    except (KeyError, TypeError, ValueError) as e:
        raise EventError(f"the pull_request payload is missing {e}") from e
