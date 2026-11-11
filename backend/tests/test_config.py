"""Configuration: loading, profile defaults, env overrides, schema validation, plugin registry, and proof that the scanners are config-driven."""
import copy, json, pathlib
import pytest, yaml
from conftest import FIXTURE_CONFIG, Project
from cdi import config as C, plugins

MIN = {"version": 1, "profile": "aspnet-angular-sqlserver",
       "repos": [{"name": "r1", "path": "src", "scanner": {"plugin": "dotnet-roslyn"}}]}


def write(tmp_path, raw):
    f = tmp_path / ".cdi" / "config.yml"
    f.parent.mkdir(exist_ok=True)
    f.write_text(yaml.safe_dump(raw))
    return f


def test_minimal_config_gets_profile_and_plugin_defaults(tmp_path):
    cfg = C.load(write(tmp_path, MIN), environ={})
    assert cfg["conventions"]["sql"]["default_schema"] == "dbo" and cfg["branches"]["base"] == "main"
    r = cfg["repos"][0]
    assert r["scanner"]["include"] == ["**/*.cs"] and r["main_branch"] == "main"      # from the plugin registry and branches.base
    assert cfg["_root"] == str(tmp_path.resolve())                                      # the parent of .cdi/


def test_user_values_beat_profile_and_lists_are_replaced(tmp_path):
    raw = copy.deepcopy(MIN)
    raw["conventions"] = {"sql": {"default_schema": "app"}, "api": {"route_attributes": ["Path"]}}
    cfg = C.load(write(tmp_path, raw), environ={})
    assert cfg["conventions"]["sql"]["default_schema"] == "app" and cfg["conventions"]["api"]["route_attributes"] == ["Path"]
    assert cfg["conventions"]["sql"]["procedure_prefixes"] == ["sp", "usp"]            # untouched keys keep the profile value


def test_env_overrides_win_and_parse_yaml_values(tmp_path):
    env = {"CDI__ci__blocking__enabled": "true", "CDI__limits__max_depth_downstream": "4", "CDI__branches__base": "trunk", "OTHER": "x"}
    cfg = C.load(write(tmp_path, MIN), environ=env)
    assert cfg["ci"]["blocking"]["enabled"] is True and cfg["limits"]["max_depth_downstream"] == 4
    assert cfg["branches"]["base"] == "trunk" and cfg["repos"][0]["main_branch"] == "trunk"


def test_config_path_can_come_from_the_environment(tmp_path):
    f = write(tmp_path, MIN)
    assert C.load(environ={"CDI_CONFIG": str(f)})["_file"] == str(f.resolve())
    assert C.load(tmp_path, environ={})["_file"] == str(f.resolve())                    # a directory works too


@pytest.mark.parametrize("mutate,needle", [
    (lambda r: r.update(version=2), "version"),
    (lambda r: r.update(surprise=1), "surprise"),
    (lambda r: r["repos"][0].update(path=""), "path"),
    (lambda r: r["repos"][0]["scanner"].update(plugin="nope"), "unknown scanner plugin"),
    (lambda r: r["repos"].append(copy.deepcopy(r["repos"][0])), "unique"),
    (lambda r: r.update(limits={"max_depth_downstream": 0}), "limits"),
    (lambda r: r.update(profile="missing"), "unknown profile"),
    (lambda r: r.update(risk={"rules": [{"id": "x", "label": "Bogus", "when": {"change": "added"}, "explain": "e", "action": "a"}]}), "not in labels"),
])
def test_invalid_configs_are_rejected_with_a_clear_message(tmp_path, mutate, needle):
    raw = copy.deepcopy(MIN)
    mutate(raw)
    with pytest.raises(C.ConfigError, match=needle):
        C.load(write(tmp_path, raw), environ={})


def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(C.ConfigError, match="config file not found"):
        C.load(tmp_path / "nope.yml", environ={})


def test_schema_is_valid_json_schema_and_documents_every_section():
    import jsonschema
    jsonschema.Draft202012Validator.check_schema(C.schema())
    assert {"repos", "conventions", "risk", "graph", "ci", "branches", "limits"} <= set(C.schema()["properties"])


def test_no_secret_value_can_be_stored(tmp_path):
    raw = copy.deepcopy(MIN)
    raw["graph"] = {"neo4j": {"password": "x"}}
    with pytest.raises(C.ConfigError):
        C.load(write(tmp_path, raw), environ={})                                        # only password_env (a variable NAME) is allowed


def test_plugin_registry():
    assert set(plugins.REGISTRY) == {"dotnet-roslyn", "ts-morph", "sql-scriptdom"}
    assert {p.layer for p in plugins.REGISTRY.values()} == {"api", "frontend", "sql"}
    with pytest.raises(KeyError, match="registered"):
        plugins.get("x")
    with pytest.raises(ValueError, match="already registered"):
        plugins.register(plugins.get("ts-morph"))


def test_scanner_view_is_written_idempotently_and_has_absolute_paths(tmp_path):
    cfg = C.load(write(tmp_path, MIN), environ={})
    d1, d2 = C.materialize(cfg), C.materialize(cfg)
    assert d1 == d2
    repos = yaml.safe_load((d1 / "repos.yml").read_text())["repos"]
    assert repos[0]["path"] == str(tmp_path.resolve() / "src") and repos[0]["plugin"] == "dotnet-roslyn"
    assert (d1 / "routes.yml").is_file() and (d1 / "naming.yml").is_file()
    assert "sql_access" in yaml.safe_load((d1 / "naming.yml").read_text())


def test_fixture_config_loads():
    cfg = C.load(FIXTURE_CONFIG, environ={})
    assert [r["name"] for r in cfg["repos"]] == ["web", "api", "db"] and cfg["graph"]["neo4j"]["uri"].endswith(":7688")


# ---- the scanners read their pattern lists from config (mutation checks: change the list, the result must change) -----------------------------

def edge_types(frag):
    return {e["type"] for e in frag["edges"]}


def tweak_conventions(extra):
    def tweak(path):
        f = path / ".cdi/config.yml"
        f.write_text(f.read_text() + yaml.safe_dump({"conventions": extra}))
    return tweak


def test_roslyn_sql_command_types_come_from_config(tmp_path_factory, project):
    sql_types = {"CALLS_PROCEDURE", "EXECUTES_DYNAMIC_SQL", "EXECUTES_INLINE_SQL"}
    count = lambda f: sum(e["type"] in sql_types for e in f["edges"])
    base = project.scan("api")[1]
    assert count(base) > 0
    p = Project(tmp_path_factory.mktemp("cmdtypes"), tweak_conventions({"sql_access": {"command_types": ["NoSuchCommand"]}}))
    assert count(p.scan("api")[1]) == 0


def test_scriptdom_dynamic_exec_names_come_from_config(tmp_path_factory, project):
    base = project.scan("db")[1]
    assert any(e["type"] == "EXECUTES_DYNAMIC_SQL" for e in base["edges"])
    p = Project(tmp_path_factory.mktemp("dynexec"), tweak_conventions({"sql": {"dynamic_exec_procedures": ["not_a_proc"]}}))
    mut = p.scan("db")[1]
    assert not any(e["type"] == "EXECUTES_DYNAMIC_SQL" for e in mut["edges"])


def test_tsmorph_test_function_names_come_from_config(tmp_path_factory, project):
    base = project.scan("web")[1]
    assert any(n["kind"] == "TEST" for n in base["nodes"])
    p = Project(tmp_path_factory.mktemp("tsfn"), tweak_conventions({"frontend": {"test_functions": {"suite": ["suite"], "case": ["test"]}}}))
    mut = p.scan("web")[1]
    assert not any(n["kind"] == "TEST" for n in mut["nodes"])


def test_linker_default_schema_comes_from_config(full):
    from cdi.linker.graphio import Graph, load_config
    from cdi.linker.link import Linker
    g = Graph.from_fragments([full["web"], full["api"], full["db"]])
    assert Linker(g, load_config(FIXTURE_CONFIG)).default_schema == "dbo"
    assert Linker(g, load_config(FIXTURE_CONFIG, environ={"CDI__conventions__sql__default_schema": "app"})).default_schema == "app"


# ---- the scanner-view temp directory: created per process, removed when the run ends --------------------------------------------------------
import os, subprocess, sys, tempfile


def _view_dirs(root):
    return sorted(p.name for p in pathlib.Path(root).iterdir() if p.name.startswith(C.CONFIG_DIR_PREFIX))


def test_materialize_is_private_per_process_and_cached_within_it(tmp_path):
    cfg = C.load(write(tmp_path, MIN), environ={})
    d1, d2 = C.materialize(cfg), C.materialize(cfg)
    assert d1 == d2 and d1.parent.resolve() == pathlib.Path(tempfile.gettempdir()).resolve() and d1.name.startswith(C.CONFIG_DIR_PREFIX)
    assert not d1.is_symlink() and (d1.stat().st_mode & 0o077) == 0, "a private directory (mode 0700), never shared with another process"
    assert {p.name for p in d1.iterdir()} == set(C.VIEW_FILES)


def test_cleanup_removes_exactly_the_directory_it_created(tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"; tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    other = tmp / (C.CONFIG_DIR_PREFIX + "someone-elses"); other.mkdir(); (other / "repos.yml").write_text("x")        # not ours: must survive
    unrelated = tmp / "keep-me"; unrelated.mkdir()
    cfg = C.load(write(tmp_path, MIN), environ={})
    d = C.materialize(cfg)
    assert d.parent == tmp.resolve() or d.parent == tmp
    assert C.cleanup_materialized() == [str(d)]
    assert not d.exists() and other.is_dir() and (other / "repos.yml").is_file() and unrelated.is_dir()
    assert C.cleanup_materialized() == [], "a second cleanup does nothing"
    assert not C._MATERIALIZED


def test_cleanup_refuses_symlinks_foreign_places_and_unexpected_content(tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"; tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    victim = tmp_path / "victim"; victim.mkdir()
    for n in C.VIEW_FILES:
        (victim / n).write_text("precious")
    link = tmp / (C.CONFIG_DIR_PREFIX + "link"); link.symlink_to(victim, target_is_directory=True)
    assert C._remove_created_dir(link) is False and all((victim / n).read_text() == "precious" for n in C.VIEW_FILES)
    nested = tmp / "sub" / (C.CONFIG_DIR_PREFIX + "nested"); nested.mkdir(parents=True)
    C._MATERIALIZED["k1"] = nested
    assert C._remove_created_dir(nested) is False and nested.is_dir(), "not a direct child of the temp dir"
    cfg = C.load(write(tmp_path, MIN), environ={})
    d = C.materialize(cfg)
    (d / "extra.txt").write_text("user data")
    assert C._remove_created_dir(d) is False and (d / "extra.txt").is_file(), "never removes content it did not write"
    wrong = tmp / "other-name"; wrong.mkdir()
    C._MATERIALIZED["k2"] = wrong
    assert C._remove_created_dir(wrong) is False and wrong.is_dir()
    C._MATERIALIZED.clear()


@pytest.mark.parametrize("ending", ["raise SystemExit(0)", "raise SystemExit(3)", "raise RuntimeError('boom')"])
def test_the_directory_is_gone_after_the_process_ends_even_on_failure(tmp_path, ending):
    cfgf = write(tmp_path, MIN)
    sandbox = tmp_path / "t"; sandbox.mkdir()
    code = f"from cdi import config as C; cfg = C.load({str(cfgf)!r}); d = C.materialize(cfg); print(d); {ending}"
    r = subprocess.run([sys.executable, "-c", code], env={**os.environ, "TMPDIR": str(sandbox)}, capture_output=True, text=True)
    printed = r.stdout.strip().splitlines()[-1]
    assert printed.startswith(str(sandbox.resolve())) or printed.startswith(str(sandbox))
    assert _view_dirs(sandbox) == [], f"leftover: {_view_dirs(sandbox)}"


def test_sigterm_in_a_cli_run_still_cleans_up(tmp_path):
    """cdi.cli.main installs a SIGTERM handler that exits normally, so the atexit cleanup runs."""
    cfgf = write(tmp_path, MIN)
    sandbox = tmp_path / "t"; sandbox.mkdir()
    code = (f"import os, signal, time; from cdi import config as C, cli; cfg = C.load({str(cfgf)!r}); C.materialize(cfg); "
            f"cli.main(['config', 'profiles']); os.kill(os.getpid(), signal.SIGTERM); time.sleep(10)")
    r = subprocess.run([sys.executable, "-c", code], env={**os.environ, "TMPDIR": str(sandbox)}, capture_output=True, text=True, timeout=60)
    assert r.returncode == 143, r.stderr
    assert _view_dirs(sandbox) == []
