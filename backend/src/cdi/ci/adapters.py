"""Posting adapters. FileSink (default) writes the files. AzureDevOpsAdapter is WRITTEN BUT NEVER EXECUTED in this PoC: it is disabled unless
--enable-azure-adapter is passed, reads its token only from an environment variable, and every network call goes through an injectable transport
(tests use fakes; the default transport is only built when the adapter is enabled). Nothing here has been run against a real service."""
from __future__ import annotations
import base64, json, os, pathlib
from typing import Callable, Optional
from . import payloads


class AdapterDisabled(RuntimeError):
    pass


class PostingAdapter:
    """Interface: publish a comment (idempotently, keyed by `marker`) and a status."""
    def post(self, pr_name: str, comment_md: str, status: dict, marker: str) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


class FileSink(PostingAdapter):
    """Default. Overwrites out/pr-comment.md and out/pr-status.json every run (so it is naturally idempotent)."""
    def __init__(self, out_dir):
        self.out = pathlib.Path(out_dir)

    def post(self, pr_name, comment_md, status, marker):
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "pr-comment.md").write_text(comment_md)
        doc = {"simulated": True, "shape_verified_against_real_service": False,
               "note": "Shapes follow the public Azure DevOps REST docs (api-version 7.1); nothing was posted anywhere.",
               "thread": payloads.thread_payload(comment_md, marker), "status": status}
        (self.out / "pr-status.json").write_text(json.dumps(doc, indent=2))
        return {"adapter": "file", "files": [str(self.out / "pr-comment.md"), str(self.out / "pr-status.json")]}


class AzureDevOpsAdapter(PostingAdapter):
    def __init__(self, azure_cfg: dict, pull_request_id: Optional[int], enabled: bool = False, transport: Optional[Callable] = None, environ=None):
        self.cfg, self.pr_id, self.enabled = azure_cfg, pull_request_id, enabled
        self._transport, self._environ = transport, (os.environ if environ is None else environ)

    # ---- guards: nothing below runs unless explicitly enabled ----
    def _require_enabled(self):
        if not self.enabled:
            raise AdapterDisabled("Azure DevOps adapter is disabled; pass --enable-azure-adapter to allow it (it has never been run against a real service)")
        if not self.pr_id:
            raise AdapterDisabled("pull request id is required (--pull-request-id)")
        for k in ("organization", "project", "repository_id"):
            if str(self.cfg.get(k, "")).startswith("<"):
                raise AdapterDisabled(f".cdi/config.yml ci.adapter.azure.{k} is still a placeholder")

    def _token(self):
        tok = self._environ.get(self.cfg["token_env"])
        if not tok:
            raise AdapterDisabled(f"environment variable {self.cfg['token_env']} is not set")
        return tok

    def _base(self):
        c = self.cfg
        return (f"https://dev.azure.com/{c['organization']}/{c['project']}/_apis/git/repositories/{c['repository_id']}"
                f"/pullRequests/{self.pr_id}")

    def _headers(self):
        tok = self._token()
        if self.cfg.get("auth_scheme", "basic") == "bearer":
            auth = f"Bearer {tok}"
        else:
            auth = "Basic " + base64.b64encode(f":{tok}".encode()).decode()
        return {"Authorization": auth, "Content-Type": "application/json"}

    def _call(self, method, url, body=None):
        headers = self._headers()
        if self._transport is None:                      # the real transport exists only once the adapter is enabled
            import urllib.request
            def transport(m, u, h, b):
                req = urllib.request.Request(u, data=(json.dumps(b).encode() if b is not None else None), headers=h, method=m)
                with urllib.request.urlopen(req, timeout=30) as r:   # pragma: no cover - never executed here
                    return r.status, json.loads(r.read().decode() or "null")
            self._transport = transport
        return self._transport(method, url, headers, body)

    # ---- idempotent thread handling ----
    def find_own_thread(self, marker):
        """List the PR's threads (GET .../threads) and return (thread_id, comment_id) of the first live thread whose first comment carries the marker."""
        self._require_enabled()
        v = self.cfg["api_version"]
        status, data = self._call("GET", f"{self._base()}/threads?api-version={v}")
        for t in (data or {}).get("value", []):
            if t.get("isDeleted"):
                continue
            for c in t.get("comments", []):
                if not c.get("isDeleted") and marker in (c.get("content") or ""):
                    return t["id"], c["id"]
            prop = ((t.get("properties") or {}).get("cdiPocMarker") or {}).get("$value")
            if prop == marker:
                live = [c for c in t.get("comments", []) if not c.get("isDeleted")]
                if live:
                    return t["id"], live[0]["id"]
        return None

    def upsert_comment(self, comment_md, marker):
        self._require_enabled()
        v = self.cfg["api_version"]
        found = self.find_own_thread(marker)
        if found:
            tid, cid = found
            self._call("PATCH", f"{self._base()}/threads/{tid}/comments/{cid}?api-version={v}", payloads.comment_update_payload(comment_md))
            return {"action": "updated", "thread_id": tid, "comment_id": cid}
        _, data = self._call("POST", f"{self._base()}/threads?api-version={v}", payloads.thread_payload(comment_md, marker))
        return {"action": "created", "thread_id": (data or {}).get("id")}

    def post_status(self, status):
        self._require_enabled()
        return self._call("POST", f"{self._base()}/statuses?api-version={self.cfg['api_version']}", status)

    def post(self, pr_name, comment_md, status, marker):
        res = self.upsert_comment(comment_md, marker)
        self.post_status(status)
        return {"adapter": "azure", **res}


def build_adapter(name, ci_cfg, out_dir, enable_azure=False, pull_request_id=None, transport=None, environ=None):
    """Default is the file sink. The Azure adapter object is only returned for name == 'azure'; it is still disabled unless enable_azure is set."""
    if name in (None, "file"):
        return FileSink(out_dir)
    if name == "azure":
        return AzureDevOpsAdapter(ci_cfg["adapter"]["azure"], pull_request_id, enabled=enable_azure, transport=transport, environ=environ)
    raise ValueError(f"unknown adapter {name!r}")
