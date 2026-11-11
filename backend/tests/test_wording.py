"""No fixed claim about a particular sample in the tool's source: wording about synthetic data comes from the `synthetic` flag set by the repository's configuration."""
import pathlib, re
from conftest import BACKEND, ROOT

FORBIDDEN = [r"small synthetic", r"synthetic-extended", r"synthetic-scale", r"this synthetic sample", r"synthetic sample", r"SYNTHETIC-extended"]


def test_backend_source_has_no_hardcoded_claims_about_a_synthetic_sample():
    hits = []
    for f in sorted((BACKEND / "src").rglob("*")):
        if f.suffix not in (".py", ".yml", ".json") or "__pycache__" in f.parts:
            continue
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if any(re.search(p, line, re.I) for p in FORBIDDEN):
                hits.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()[:100]}")
    assert hits == [], "\n".join(hits)


def test_frontend_page_takes_its_notice_from_the_data():
    app = (ROOT / "frontend/src/App.tsx").read_text()
    assert "data.meta.notice" in app and "Synthetic sample data" not in app
