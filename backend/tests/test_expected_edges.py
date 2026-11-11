"""Scanner output vs the HAND-WRITTEN tests/expected_edges.yml (synthetic sample)."""
import pathlib, yaml
import compare_expected as ce

SPEC = pathlib.Path(__file__).with_name("expected_edges.yml")


def test_scanner_output_matches_hand_written_expectations(full, capsys):
    res = ce.compare(full, yaml.safe_load(SPEC.read_text()))
    text, recall = ce.report(res)
    print("\n" + text)
    assert not res["violations"], res["violations"]
    assert not res["test_mismatch"], res["test_mismatch"]
    assert not res["missing"], f"recall {recall:.1%}; missing: {res['missing']}"
    assert recall == 1.0


def test_expected_file_is_hand_written_not_generated():
    head = SPEC.read_text().splitlines()[0]
    assert "HAND-WRITTEN" in head
