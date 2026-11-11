"""Minimal GitHub REST client (urllib). The token is only ever sent in the Authorization header and never logged.
API base URL comes from GITHUB_API_URL (GitHub Enterprise Server) or defaults to https://api.github.com; tests point it at a local fake server."""
from __future__ import annotations
import json, urllib.error, urllib.request

DEFAULT_API = "https://api.github.com"
API_VERSION = "2022-11-28"


class GitHubError(Exception):
    def __init__(self, status, message, method="", path=""):
        self.status, self.message, self.method, self.path = status, message, method, path
        super().__init__(f"{method} {path}: HTTP {status}: {message}")


class Client:
    def __init__(self, token, api_url=None, timeout=30):
        self.token, self.api, self.timeout = token, (api_url or DEFAULT_API).rstrip("/"), timeout

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.api + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "cdi", **({"Content-Type": "application/json"} if data else {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read() or b"{}").get("message", e.reason)
            except (json.JSONDecodeError, ValueError):
                msg = str(e.reason)
            raise GitHubError(e.code, msg, method, path) from None
        except urllib.error.URLError as e:
            raise GitHubError(0, f"cannot reach {self.api}: {e.reason}", method, path) from None

    def get_all(self, path, per_page=100, max_pages=20):
        out, page = [], 1
        sep = "&" if "?" in path else "?"
        while page <= max_pages:
            _, items = self.request("GET", f"{path}{sep}per_page={per_page}&page={page}")
            out += items or []
            if len(items or []) < per_page:
                break
            page += 1
        return out
