"""config.example/config.yml must stay a valid, loadable configuration."""
from conftest import ROOT
from cdi import config as C


def test_example_config_is_valid():
    cfg = C.load(ROOT / "config.example/config.yml", environ={})
    assert [r["name"] for r in cfg["repos"]] == ["web", "api", "db"] and cfg["graph"]["store"] == "json"
    assert cfg["ci"]["blocking"]["enabled"] is False
