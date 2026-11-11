"""The `cdi` command: every command exists, is documented in --help, and dispatches; no sample-specific names."""
import pytest
from cdi import cli

EXPECTED = ["baseline", "pr", "export", "serve", "audit", "config"]


def test_top_level_help_lists_every_command_with_a_description(capsys):
    assert cli.main(["--help"]) == 0 and cli.main([]) == 0
    out = capsys.readouterr().out
    for name in EXPECTED + ["github"]:
        assert name in cli.COMMANDS
        assert f"  {name}" in out and cli.COMMANDS[name][1] in out
    assert "cdi <command> --help" in out and ".cdi/config.yml" in out


@pytest.mark.parametrize("name", EXPECTED + ["github"])
def test_each_command_has_its_own_help(name, capsys):
    assert cli.main([name, "--help"]) == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower() and len(out.splitlines()) >= 4, f"`cdi {name} --help` printed almost nothing"


def test_help_documents_the_options_that_matter(capsys):
    cli.main(["serve", "--help"]); out = capsys.readouterr().out
    assert "127.0.0.1" in out and "--token-env" in out and "--cors-origin" in out and "--store-path" in out
    cli.main(["baseline", "--help"]); out = capsys.readouterr().out
    assert "full" in out and "incremental" in out and "--store" in out
    cli.main(["pr", "--help"]); out = capsys.readouterr().out
    assert "--pr" in out and "--target" in out and "branches.base" in out
    cli.main(["export", "--help"]); out = capsys.readouterr().out
    assert "--source" in out and "--reports-dir" in out


def test_unknown_command_and_missing_arguments_are_errors(capsys):
    assert cli.main(["frobnicate"]) == 2 and "unknown command" in capsys.readouterr().err
    assert cli.main(["baseline"]) == 2                    # the mode is required
    assert cli.main(["pr"]) == 2                          # --pr is required


def test_serve_through_the_cli_refuses_an_open_bind_without_a_token(capsys, monkeypatch):
    monkeypatch.delenv("CDI_API_TOKEN", raising=False)
    assert cli.main(["serve", "--host", "0.0.0.0"]) == 1
    assert "without authentication" in capsys.readouterr().err


def test_config_and_audit_still_work_through_the_cli(capsys):
    from conftest import FIXTURE_CONFIG, ROOT
    assert cli.main(["config", "validate", "--file", str(FIXTURE_CONFIG)]) == 0
    assert cli.main(["config", "schema"]) == 0 and '"conventions"' in capsys.readouterr().out
    assert cli.main(["audit", "--root", str(ROOT)]) == 0
