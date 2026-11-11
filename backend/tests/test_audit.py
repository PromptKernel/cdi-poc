"""The hardcoding audit: clean on this repository, and it really catches planted identifiers."""
import importlib.util, json, pathlib, shutil
from conftest import ROOT, BACKEND
from cdi import cli

spec = importlib.util.spec_from_file_location("audit_hardcoding", BACKEND / "tools" / "audit_hardcoding.py")
A = importlib.util.module_from_spec(spec); spec.loader.exec_module(A)


def mini_repo(tmp_path):
    (tmp_path / "backend/src/cdi").mkdir(parents=True)
    (tmp_path / "frontend/src").mkdir(parents=True)
    return tmp_path


def test_this_repository_is_clean():
    res = A.audit(ROOT)
    assert res["files_scanned"] > 50 and res["terms"] >= 8
    assert res["hits"] == [], res["hits"][:5]


def test_planted_identifiers_are_found_with_file_and_line(tmp_path):
    r = mini_repo(tmp_path)
    (r / "backend/src/cdi/a.py").write_text("x = 1\nTABLE = 'tblEmployee'\n")
    (r / "frontend/src/b.ts").write_text("// see ASPCoreWithAngular\nconst p = 'samples/web'\n")
    (r / "backend/src/cdi/c.py").write_text("name = 'Department'\n")
    hits = {(h["file"], h["line"], h["category"]) for h in A.audit(r)["hits"]}
    assert ("backend/src/cdi/a.py", 2, "domain") in hits
    assert ("frontend/src/b.ts", 1, "upstream") in hits and ("frontend/src/b.ts", 2, "layout") in hits
    assert ("backend/src/cdi/c.py", 1, "domain") in hits


def test_allow_marker_and_skipped_areas(tmp_path):
    r = mini_repo(tmp_path)
    (r / "backend/src/cdi/a.py").write_text("x = 'employee'  # audit:allow(documented example)\n")
    (r / "backend/tests").mkdir(); (r / "backend/tests/t.py").write_text("x = 'employee'\n")        # fixtures may use sample names
    (r / "frontend/node_modules/m").mkdir(parents=True); (r / "frontend/node_modules/m/i.js").write_text("employee")
    assert A.audit(r)["hits"] == []


def test_cli_exit_codes(tmp_path, capsys):
    r = mini_repo(tmp_path)
    assert cli.main(["audit", "--root", str(r)]) == 0
    (r / "backend/src/cdi/a.py").write_text("x = 'employee'\n")
    assert cli.main(["audit", "--root", str(r)]) == 1
    assert "1 hit" in capsys.readouterr().out
    assert cli.main(["audit", "--root", str(r), "--json"]) == 1


def test_cli_config_commands(capsys):
    from conftest import FIXTURE_CONFIG
    assert cli.main(["config", "validate", "--file", str(FIXTURE_CONFIG)]) == 0
    assert cli.main(["config", "profiles"]) == 0 and "aspnet-angular-sqlserver" in capsys.readouterr().out
    assert cli.main(["config", "validate", "--file", "/nonexistent.yml"]) == 2
