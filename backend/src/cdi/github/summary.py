"""Job summary (GITHUB_STEP_SUMMARY, Markdown, 1 MiB per step) and workflow-command annotations.

GitHub offers no API to read a job summary, so `write()` also prints it into the job log between ::group:: markers. Because the text contains
names taken from pull-request files, it is printed safely: workflow commands are switched off for the duration (::stop-commands:: with a random
resume token) and every line is indented, so nothing in it can act as a command. Anything that looks like a credential (the token, an Authorization
header, a GitHub token pattern) is replaced by *** before the text goes anywhere."""
from __future__ import annotations
import os, re, secrets, sys

SUMMARY_LIMIT = 1024 * 1024        # per-step limit stated in the workflow-commands docs
TOKEN_PATTERNS = [
    re.compile(r"(?i)authorization\s*[:=]\s*\S+(?:\s+\S+)?"),             # an Authorization header or assignment, with its scheme and value
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
]
SECRET_ENV = ("GITHUB_TOKEN", "CDI_API_TOKEN")


def escape_data(s: str) -> str:
    return str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def redact(text: str, secrets_: list[str]) -> str:
    for s in sorted({s for s in secrets_ if s and len(s) >= 6}, key=len, reverse=True):
        text = text.replace(s, "***")
    for rx in TOKEN_PATTERNS:
        text = rx.sub("***", text)
    return text


class Summary:
    def __init__(self, environ=None, stream=None):
        env = os.environ if environ is None else environ
        self.path = env.get("GITHUB_STEP_SUMMARY")
        self.secrets = [env.get(k, "") for k in SECRET_ENV]
        self.lines: list[str] = []
        self.stream = stream if stream is not None else sys.stdout

    def _clean(self, s):
        return redact(str(s), self.secrets)

    def add(self, *lines):
        self.lines += [self._clean(l) for l in lines]

    def warning(self, msg, title=None):
        """Printed as a workflow command (an annotation on the run) and repeated in the summary."""
        t = f" title={escape_data(self._clean(title))}" if title else ""          # syntax: ::warning title=T::message (properties after a space, comma separated)
        print(f"::warning{t}::{escape_data(self._clean(msg))}", file=self.stream)
        self.lines.append(f"> :warning: {self._clean(msg)}")

    def notice(self, msg):
        print(f"::notice::{escape_data(self._clean(msg))}", file=self.stream)

    def text(self):
        return "\n".join(self.lines) + "\n"

    def echo(self, title="cdi job summary", text=None):
        """Print text (default: the summary) into the log, inert: see the module docstring."""
        marker = secrets.token_hex(16)
        body = self.text() if text is None else self._clean(text)
        print(f"::group::{title}", file=self.stream)
        print(f"::stop-commands::{marker}", file=self.stream)
        for line in body.splitlines():
            print("  " + line, file=self.stream)
        print(f"::{marker}::", file=self.stream)
        print("::endgroup::", file=self.stream)

    def write(self):
        body = self.text().encode()[:SUMMARY_LIMIT].decode(errors="ignore")
        if self.path:
            with open(self.path, "a") as f:
                f.write(body)
            self.echo()
        else:
            print(body, file=self.stream)
