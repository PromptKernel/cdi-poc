#!/usr/bin/env python3
"""Audit: no sample-specific identifier may appear in the tool's own source (backend/ and frontend/).

Scans backend/{src,scanners,scripts,schema,deploy} and frontend/ (minus build output) for the vocabulary in audit_terms.txt.
Not scanned: backend/tests (the pinned fixture legitimately uses the sample's names), node_modules, bin/obj/dist, lock files,
this tool and its terms file. A line containing `audit:allow` (with a reason) is skipped.
Exit status 1 when anything is found. Run it with `cdi audit` or `python backend/tools/audit_hardcoding.py [--root REPO] [--json]`."""
from __future__ import annotations
import argparse, json, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
SCAN_ROOTS = ["backend/src", "backend/scanners", "backend/scripts", "backend/schema", "backend/deploy", "backend/pyproject.toml",
              "backend/requirements.txt", "backend/pytest.ini", "frontend"]
SKIP_DIRS = {"node_modules", "bin", "obj", "dist", "test-results", "__pycache__", ".pytest_cache", ".venv", "playwright-report"}
SKIP_FILES = {"package-lock.json", "audit_hardcoding.py", "audit_terms.txt"}
TEXT_SUFFIXES = {".py", ".cs", ".csproj", ".mjs", ".js", ".ts", ".tsx", ".json", ".yml", ".yaml", ".sh", ".md", ".toml", ".txt", ".ini",
                 ".html", ".css", ".sql"}
ALLOW = "audit:allow"


def load_terms(path=HERE / "audit_terms.txt"):
    terms = []
    for n, line in enumerate(pathlib.Path(path).read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cat, _, rx = line.partition("\t")
        if not rx:
            raise SystemExit(f"{path}:{n}: expected '<category><TAB><regex>'")
        terms.append((cat.strip(), re.compile(rx.strip(), re.I if cat.strip() != "sql-object" else 0)))
    return terms


def files_under(root: pathlib.Path):
    for rel in SCAN_ROOTS:
        p = root / rel
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not (set(f.relative_to(root).parts) & SKIP_DIRS) and f.name not in SKIP_FILES and f.suffix in TEXT_SUFFIXES:
                    yield f


def audit(root, terms=None):
    root = pathlib.Path(root).resolve()
    terms = terms or load_terms()
    hits, scanned = [], 0
    for f in files_under(root):
        scanned += 1
        try:
            lines = f.read_text().splitlines()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(lines, 1):
            if ALLOW in line:
                continue
            for cat, rx in terms:
                m = rx.search(line)
                if m:
                    hits.append({"file": str(f.relative_to(root)), "line": i, "category": cat, "match": m.group(0), "text": line.strip()[:140]})
    return {"root": str(root), "files_scanned": scanned, "terms": len(terms), "hits": hits}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(HERE.parents[1]), help="tool repository root (default: this repository)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = audit(a.root)
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        by_cat: dict[str, int] = {}
        for h in res["hits"]:
            by_cat[h["category"]] = by_cat.get(h["category"], 0) + 1
            print(f"{h['file']}:{h['line']}: [{h['category']}] {h['match']!r}: {h['text']}")
        print(f"audit: scanned {res['files_scanned']} files against {res['terms']} patterns: "
              f"{len(res['hits'])} hit(s)" + (f" ({', '.join(f'{k}={v}' for k, v in sorted(by_cat.items()))})" if by_cat else " - clean"))
    return 1 if res["hits"] else 0


if __name__ == "__main__":
    sys.exit(main())
