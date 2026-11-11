"""Job summary (GITHUB_STEP_SUMMARY, Markdown, 1 MiB per step) and workflow-command annotations."""
from __future__ import annotations
import os, sys

SUMMARY_LIMIT = 1024 * 1024        # per-step limit stated in the workflow-commands docs


def escape_data(s: str) -> str:
    return str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


class Summary:
    def __init__(self, environ=None, stream=None):
        env = os.environ if environ is None else environ
        self.path = env.get("GITHUB_STEP_SUMMARY")
        self.lines: list[str] = []
        self.stream = stream if stream is not None else sys.stdout

    def add(self, *lines):
        self.lines += list(lines)

    def warning(self, msg, title=None):
        """Printed as a workflow command (an annotation on the run) and repeated in the summary."""
        t = f" title={escape_data(title)}" if title else ""          # syntax: ::warning title=T::message (properties after a space, comma separated)
        print(f"::warning{t}::{escape_data(msg)}", file=self.stream)
        self.lines.append(f"> :warning: {msg}")

    def notice(self, msg):
        print(f"::notice::{escape_data(msg)}", file=self.stream)

    def text(self):
        return "\n".join(self.lines) + "\n"

    def write(self):
        body = self.text().encode()[:SUMMARY_LIMIT].decode(errors="ignore")
        if self.path:
            with open(self.path, "a") as f:
                f.write(body)
        else:
            print(body, file=self.stream)
