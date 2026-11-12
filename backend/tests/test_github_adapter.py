"""GitHub adapter against the in-memory fake server: upsert by marker, status, size limits, 403/404/422 as advisory failures."""
import pytest
from fake_github import FakeGitHub, TOKEN
from cdi.ci import payloads
from cdi.github import adapter as A, event as E
from cdi.github.client import Client, GitHubError
from cdi.github.summary import Summary

SHA = "a" * 40
MARK = "cdi:impact-report"


def body(text="hello"):
    return f"{payloads.marker_text(MARK, 'pr-7')}\n## Dependency impact\n{text}\n"


def status(state="succeeded", desc="advisory: 1 changed object(s)"):
    return payloads.status_payload(state, desc, {"name": "cdi/impact-analysis", "genre": "cdi"}, 140)


@pytest.fixture()
def gh():
    with FakeGitHub() as f:
        yield f


def adapter(gh, token=TOKEN, **kw):
    return A.GitHubAdapter(Client(token, gh.url), "o/r", 7, SHA, **kw)


def test_creates_one_comment_and_sets_the_status(gh):
    res = adapter(gh).post("pr-7", body(), status(), MARK)
    assert res["errors"] == [] and res["comment"]["action"] == "created" and res["status"] == {"state": "success", "context": "cdi/impact-analysis"}
    assert len(gh.comments[7]) == 1 and MARK in gh.comments[7][0]["body"]
    assert gh.statuses == [{"sha": SHA, "state": "success", "description": "advisory: 1 changed object(s)", "context": "cdi/impact-analysis"}]


def test_second_run_updates_the_same_comment_not_a_new_one(gh):
    a = adapter(gh)
    a.post("pr-7", body("first"), status(), MARK)
    cid = gh.comments[7][0]["id"]
    res = a.post("pr-7", body("second"), status(), MARK)
    assert res["comment"] == {"action": "updated", "id": cid, "url": gh.comments[7][0]["html_url"]}
    assert len(gh.comments[7]) == 1 and "second" in gh.comments[7][0]["body"]
    assert [m for m, _ in gh.requests].count("POST") == 3          # 1 create + 2 statuses; the comment was PATCHed
    res = a.post("pr-7", body("second"), status(), MARK)            # identical body: no write at all
    assert res["comment"]["action"] == "unchanged"
    assert sum(1 for m, p in gh.requests if m == "PATCH") == 1, "the identical third run wrote nothing"


def test_only_the_workflows_own_comment_is_ever_edited(gh):
    gh.add_comment(7, body("pasted by a user"), login="some-user", type_="User")
    res = adapter(gh).post("pr-7", body("mine"), status(), MARK)
    assert res["comment"]["action"] == "created" and len(gh.comments[7]) == 2
    assert gh.comments[7][0]["body"] == body("pasted by a user"), "someone else's comment is untouched"


def test_duplicate_own_comments_are_reported_and_left_alone(gh):
    gh.add_comment(7, body("old 1")); gh.add_comment(7, body("old 2"))
    res = adapter(gh).post("pr-7", body("new"), status(), MARK)
    assert res["comment"]["action"] == "updated" and len(res["duplicates_left_untouched"]) == 1
    assert "new" in gh.comments[7][0]["body"] and "old 2" in gh.comments[7][1]["body"]


def test_pagination_finds_the_marker_beyond_the_first_page(gh):
    for i in range(130):
        gh.add_comment(7, f"unrelated {i}", login="someone", type_="User")
    gh.add_comment(7, body("old"))
    res = adapter(gh).post("pr-7", body("new"), status(), MARK)
    assert res["comment"]["action"] == "updated" and len(gh.comments[7]) == 131


def test_oversized_comment_is_truncated_to_the_limit_and_accepted(gh):
    big = body("x" * 80000)
    res = adapter(gh).post("pr-7", big, status(), MARK)
    assert res["truncated"] and res["errors"] == []
    posted = gh.comments[7][0]["body"]
    assert len(posted) <= A.COMMENT_HARD_CAP and posted.startswith("<!-- cdi:impact-report:v1") and "truncated" in posted


def test_long_status_description_is_cut_to_140(gh):
    res = adapter(gh).post("pr-7", body(), {**status(), "description": "d" * 300}, MARK)
    assert res["errors"] == [] and len(gh.statuses[0]["description"]) == 140


@pytest.mark.parametrize("state,expected", [("succeeded", "success"), ("failed", "failure"), ("error", "error"), ("pending", "pending"), ("notApplicable", "success")])
def test_status_states_map_to_github_states(gh, state, expected):
    adapter(gh).post("pr-7", body(), status(state), MARK)
    assert gh.statuses[-1]["state"] == expected


@pytest.mark.parametrize("code,needle", [(403, "pull-requests: write"), (404, "not visible"), (422, "Validation failed")])
def test_comment_write_failures_are_advisory_with_a_clear_message(gh, code, needle):
    gh.deny["comments"] = code
    res = adapter(gh).post("pr-7", body(), status(), MARK)                 # does not raise
    assert res["comment"] is None and any("comment" in e and needle in e and str(code) in e for e in res["errors"]), res["errors"]
    assert res["status"] is not None, "the status is still attempted"


@pytest.mark.parametrize("code,needle", [(403, "statuses: write"), (404, "not visible"), (422, "Validation failed")])
def test_status_failures_are_advisory_with_a_clear_message(gh, code, needle):
    gh.deny["statuses"] = code
    res = adapter(gh).post("pr-7", body(), status(), MARK)
    assert res["comment"]["action"] == "created" and res["status"] is None
    assert any("commit status" in e and needle in e for e in res["errors"]), res["errors"]


def test_read_failure_on_listing_comments_is_reported(gh):
    gh.deny_read = 403
    res = adapter(gh).post("pr-7", body(), status(), MARK)
    assert any("403" in e for e in res["errors"]) and res["status"] is not None


def test_bad_token_and_unreachable_server_are_advisory(gh):
    res = adapter(gh, token="wrong").post("pr-7", body(), status(), MARK)
    assert len(res["errors"]) == 2 and all("401" in e for e in res["errors"])
    res = A.GitHubAdapter(Client(TOKEN, "http://127.0.0.1:1"), "o/r", 7, SHA).post("pr-7", body(), status(), MARK)
    assert len(res["errors"]) == 2 and all("cannot reach" in e for e in res["errors"])


def test_the_token_is_never_in_results_or_errors(gh):
    gh.deny["comments"] = 403
    res = adapter(gh).post("pr-7", body(), status(), MARK)
    assert TOKEN not in repr(res)


# ---- event parsing and summary -------------------------------------------------------------------------------------------------------

def pr_event(**over):
    pr = {"number": 7, "base": {"ref": "main", "sha": "b" * 40, "repo": {"full_name": "o/r"}},
          "head": {"ref": "feature", "sha": SHA, "repo": {"full_name": "o/r"}}}
    pr.update(over)
    return {"action": "synchronize", "pull_request": pr}


def test_event_gives_the_base_ref_and_detects_forks():
    ev = E.parse_pull_request(pr_event())
    assert (ev.number, ev.base_ref, ev.head_sha, ev.is_fork) == (7, "main", SHA, False)
    fork = E.parse_pull_request(pr_event(head={"ref": "x", "sha": SHA, "repo": {"full_name": "someone/r"}}))
    assert fork.is_fork
    assert E.parse_pull_request(pr_event(head={"ref": "x", "sha": SHA, "repo": None})).is_fork            # deleted fork
    assert not E.parse_pull_request(pr_event(head={"ref": "x", "sha": SHA, "repo": {"full_name": "O/R"}})).is_fork   # case-insensitive


@pytest.mark.parametrize("bad", [{}, {"pull_request": {}}, {"pull_request": {"number": 1, "base": {"sha": "x", "repo": {"full_name": "o/r"}}, "head": {}}}])
def test_malformed_events_are_clear_errors(bad):
    with pytest.raises(E.EventError):
        E.parse_pull_request(bad)


def test_summary_escapes_workflow_commands_and_respects_the_size_limit(tmp_path, capsys):
    f = tmp_path / "s.md"
    s = Summary({"GITHUB_STEP_SUMMARY": str(f)})
    s.warning("line1\nline2 100%", "t")
    assert "::warning title=t::line1%0Aline2 100%25" in capsys.readouterr().out
    s.add("x" * (2 * 1024 * 1024)); s.write()
    assert f.stat().st_size <= 1024 * 1024


# ---- job summary echoed into the log: inert and free of credentials ----------------------------------------------------------------------
def test_summary_is_echoed_into_the_log_inside_group_markers(tmp_path, capsys):
    f = tmp_path / "s.md"
    s = Summary({"GITHUB_STEP_SUMMARY": str(f)})
    s.add("## Dependency impact", "State: succeeded")
    s.write()
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "::group::cdi job summary" and out[-1] == "::endgroup::"
    assert out[1].startswith("::stop-commands::") and out[-2] == f"::{out[1].split('::')[2]}::"
    assert "  ## Dependency impact" in out and f.read_text() == "## Dependency impact\nState: succeeded\n"


def test_text_from_pr_files_cannot_act_as_workflow_commands(tmp_path, capsys):
    s = Summary({"GITHUB_STEP_SUMMARY": str(tmp_path / "s.md")})
    s.add("::set-output name=x::y", "::add-mask::abc", "::error::boom", "::stop-commands::fake")
    s.write()
    inner = capsys.readouterr().out.splitlines()[2:-2]            # between our own stop-commands and its resume token
    assert inner and all(l.startswith("  ") and not l.startswith("::") for l in inner)


HDR = "Author" + "ization"        # built at run time so that no literal header-with-token pattern sits in the repository


def test_no_token_or_authorization_header_can_appear_in_the_summary_or_the_log(tmp_path, capsys):
    tok = "ghs_" + "A1b2C3d4E5" * 4
    f = tmp_path / "s.md"
    s = Summary({"GITHUB_STEP_SUMMARY": str(f), "GITHUB_TOKEN": tok, "CDI_API_TOKEN": "api-token-value-xyz"})
    s.add(f"token is {tok}", f"{HDR}: Bearer abcdefghijkl", f"{HDR.lower()}=Basic Zm9vOmJhcg==", f"curl -H '{HDR}: token gh" + "p_" + "Z" * 30 + "'",
          "api-token-value-xyz in a message", f"Bearer {tok}", "github_pat_" + "q" * 30)
    s.warning(f"posting failed with {tok} and {HDR}: Bearer abcdefghijkl", f"title {tok}")
    s.write()
    out = capsys.readouterr().out
    for text in (out, f.read_text(), s.text()):
        for bad in (tok, "abcdefghijkl", "api-token-value-xyz", "Zm9vOmJhcg", "gh" + "p_ZZZ", "github_" + "pat_qqq"):
            assert bad not in text, bad
        assert "authorization" not in text.lower(), text
    assert "***" in out
