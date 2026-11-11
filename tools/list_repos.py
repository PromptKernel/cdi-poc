#!/usr/bin/env python3
"""Print 'name kind path' for each logical repo in config/repos.yml (used by pipeline scripts)."""
import pathlib, yaml
root = pathlib.Path(__file__).resolve().parents[1]
for r in yaml.safe_load((root / "config/repos.yml").read_text())["repos"]:
    print(r["name"], r["kind"], r["path"])
