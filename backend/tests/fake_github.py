"""An in-memory fake of the parts of the GitHub REST API the tool uses, served over real HTTP on 127.0.0.1 (so the real client code runs).
State lives in the object; nothing leaves the machine. Behaviours are switchable to simulate permission failures.

ASSUMPTIONS (not stated in GitHub's REST pages; community-reported): a comment body over 65536 characters and a status description over 140
characters are rejected with 422."""
import json, re, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "test-token-not-a-secret"


class FakeGitHub:
    def __init__(self, bot="github-actions[bot]"):
        self.bot = bot
        self.comments = {}          # issue number -> [comment dict]
        self.statuses = []          # [{"sha", ...payload}]
        self.requests = []          # [(method, path)]
        self.deny = {}              # "comments" | "statuses" -> HTTP code to return for writes (403/404/422)
        self.deny_read = None       # HTTP code for listing comments
        self.next_id = 1000
        self.web = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.web.server_address[1]}"
        self.thread = threading.Thread(target=self.web.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.web.shutdown(); self.web.server_close()

    def add_comment(self, issue, body, login=None, type_="Bot"):
        self.next_id += 1
        c = {"id": self.next_id, "body": body, "user": {"login": login or self.bot, "type": type_}, "html_url": f"{self.url}/c/{self.next_id}"}
        self.comments.setdefault(issue, []).append(c)
        return c

    def _handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, doc=None):
                raw = json.dumps(doc if doc is not None else {}).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers()
                self.wfile.write(raw)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n) or b"{}")

            def _route(self, method):
                path = self.path
                fake.requests.append((method, path.split("?")[0]))
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._send(401, {"message": "Bad credentials"})
                p, _, q = path.partition("?")
                m = re.fullmatch(r"/repos/([^/]+/[^/]+)/issues/(\d+)/comments", p)
                if m and method == "GET":
                    if fake.deny_read:
                        return self._send(fake.deny_read, {"message": "Resource not accessible by integration"})
                    args = dict(x.split("=") for x in q.split("&") if x)
                    per, page = int(args.get("per_page", 30)), int(args.get("page", 1))
                    items = fake.comments.get(int(m.group(2)), [])
                    return self._send(200, items[(page - 1) * per: page * per])
                if m and method == "POST":
                    if fake.deny.get("comments"):
                        return self._send(fake.deny["comments"], {"message": "Resource not accessible by integration"})
                    body = self._body()["body"]
                    if len(body) > 65536:
                        return self._send(422, {"message": "Validation Failed: body is too long (maximum is 65536 characters)"})
                    return self._send(201, fake.add_comment(int(m.group(2)), body))
                m = re.fullmatch(r"/repos/([^/]+/[^/]+)/issues/comments/(\d+)", p)
                if m and method == "PATCH":
                    if fake.deny.get("comments"):
                        return self._send(fake.deny["comments"], {"message": "Resource not accessible by integration"})
                    body = self._body()["body"]
                    if len(body) > 65536:
                        return self._send(422, {"message": "Validation Failed: body is too long (maximum is 65536 characters)"})
                    for cs in fake.comments.values():
                        for c in cs:
                            if c["id"] == int(m.group(2)):
                                if c["user"]["login"] != fake.bot:
                                    return self._send(403, {"message": "not yours"})
                                c["body"] = body
                                return self._send(200, c)
                    return self._send(404, {"message": "Not Found"})
                m = re.fullmatch(r"/repos/([^/]+/[^/]+)/statuses/([0-9a-f]{40})", p)
                if m and method == "POST":
                    if fake.deny.get("statuses"):
                        return self._send(fake.deny["statuses"], {"message": "Resource not accessible by integration"})
                    d = self._body()
                    if d.get("state") not in ("error", "failure", "pending", "success"):
                        return self._send(422, {"message": "Validation Failed: state"})
                    if len(d.get("description") or "") > 140:
                        return self._send(422, {"message": "Validation Failed: description is too long (maximum is 140 characters)"})
                    fake.statuses.append({"sha": m.group(2), **d})
                    return self._send(201, {"id": len(fake.statuses)})
                return self._send(404, {"message": "Not Found"})

            def do_GET(self): self._route("GET")
            def do_POST(self): self._route("POST")
            def do_PATCH(self): self._route("PATCH")
        return H
