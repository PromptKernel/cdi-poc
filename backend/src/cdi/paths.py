"""Locations inside the installed tool (not the target repository)."""
from __future__ import annotations
import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]       # backend/ (contains scanners/ and schema/)
SCANNERS_DIR = BACKEND_ROOT / "scanners"
SCHEMA_DIR = BACKEND_ROOT / "schema"
