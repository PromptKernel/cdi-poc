import pathlib, copy
import pytest
from cdi.impact import risk, report

ROOT = pathlib.Path(__file__).resolve().parents[2]
from conftest import FIXTURE_CONFIG
CFG = risk.load(FIXTURE_CONFIG / "risk-rules.yml")


def facts(**kw):
    base = {"change": "modified", "kind": "SQL_PROC", "in_critical_list": False, "has_consumers": False, "consumer_count": 0,
            "confirmed_path_reaches_ui": False, "inferred_path_reaches_ui": False, "reaches_api_endpoint": False,
            "introduces_unresolved": False, "has_own_unresolved": False}
    base.update(kw)
    return base


def rid(f):
    r = risk.select(CFG, f)
    return r["id"] if r else None


def test_no_rule_fires_means_no_label():
    assert risk.select(CFG, facts()) is None


def test_default_config_is_valid_and_has_no_catch_all():
    risk.validate(CFG)
    assert all(r["when"] for r in CFG["rules"])


@pytest.mark.parametrize("kw,expected", [
    ({"in_critical_list": True, "change": "removed", "has_consumers": True}, "R1-critical-object"),      # critical list beats everything
    ({"change": "removed", "has_consumers": True}, "R2-removed-with-consumers"),
    ({"introduces_unresolved": True, "has_consumers": True}, "R3-introduces-unresolved"),
    ({"confirmed_path_reaches_ui": True, "has_consumers": True}, "R4-confirmed-path-to-screen"),
    ({"inferred_path_reaches_ui": True, "has_consumers": True}, "R5-inferred-path-to-screen"),
    ({"reaches_api_endpoint": True, "has_consumers": True}, "R6-api-consumers"),
    ({"has_own_unresolved": True}, "R7-own-unresolved"),
    ({"has_consumers": True}, "R8-has-consumers"),
])
def test_first_matching_rule_wins(kw, expected):
    assert rid(facts(**kw)) == expected


def test_confirmed_wins_over_inferred_when_both_hold():
    assert rid(facts(confirmed_path_reaches_ui=True, inferred_path_reaches_ui=True, has_consumers=True)) == "R4-confirmed-path-to-screen"


def test_removed_without_consumers_does_not_match_removed_rule():
    assert rid(facts(change="removed")) is None


def test_critical_list_is_glob_matched_and_default_is_a_placeholder():
    assert risk.in_critical_list({"critical_objects": ["dbo.spPay*"]}, "dbo.spPayroll")
    assert not risk.in_critical_list({"critical_objects": ["dbo.spPay*"]}, "dbo.spOther")
    assert all("EXAMPLE_ONLY" in p for p in CFG["critical_objects"])
    assert not risk.in_critical_list(CFG, "dbo.spGetAllEmployees")


def test_min_consumers_numeric_rule_is_supported_but_unused_by_default():
    cfg = {"labels": ["Low"], "rules": [{"id": "N", "label": "Low", "when": {"min_consumers": 3}, "explain": "x", "action": "y"}]}
    risk.validate(cfg)
    assert risk.select(cfg, facts(consumer_count=3)) and not risk.select(cfg, facts(consumer_count=2))
    assert not any("min_consumers" in r["when"] for r in CFG["rules"])
    text = (FIXTURE_CONFIG / "risk-rules.yml").read_text()
    assert "min_consumers" in text and "placeholder, unvalidated" in text


def test_invalid_configs_are_rejected():
    good = copy.deepcopy(CFG)
    bad = copy.deepcopy(good); bad["rules"][0]["when"] = {"nonsense": 1}
    with pytest.raises(ValueError, match="unknown condition keys"): risk.validate(bad)
    bad = copy.deepcopy(good); bad["rules"][0]["when"] = {}
    with pytest.raises(ValueError, match="catch-all"): risk.validate(bad)
    bad = copy.deepcopy(good); bad["rules"][0]["label"] = "Severe"
    with pytest.raises(ValueError, match="not in labels"): risk.validate(bad)
    bad = copy.deepcopy(good); del bad["rules"][0]["action"]
    with pytest.raises(ValueError, match="explain"): risk.validate(bad)


def test_report_prints_the_rule_that_fired_or_no_label():
    o_with = {"risk": {"label": "High", "rule_id": "R2-removed-with-consumers", "explain": "e", "matched": "change = removed"}}
    o_without = {"risk": None}
    assert "**High**" in report.label_text(o_with) and "R2-removed-with-consumers" in report.label_text(o_with)
    t = report.label_text(o_without)
    assert "NO risk label" in t and not any(l in t for l in ("Critical", "High", "Medium", "Low"))
