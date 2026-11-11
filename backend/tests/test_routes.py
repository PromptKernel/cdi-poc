import pytest
from linker import routes

CFG = {"param_token": "{}", "case_sensitive": False, "strip_leading_slash": True}


@pytest.mark.parametrize("req,ep,want", [
    ("api/Employee/Details/{}", "api/Employee/Details/{id}", "exact"),
    ("api/Employee/Details/5", "api/Employee/Details/{id}", "exact"),          # literal where endpoint has a parameter
    ("api/Employee/Details/{}", "api/Employee/Details/{id:int}", "exact"),     # route constraint is still a parameter
    ("/api/employee/index/", "api/Employee/Index", "exact"),                   # case, leading and trailing slash
    ("api/Employee/Index?x=1", "api/Employee/Index", "exact"),                 # query string ignored
    ("api/Employee/{}", "api/Employee/Index", "partial"),                      # runtime segment where endpoint is literal
    ("api/Employee/Index", "api/Employee/Details/{id}", None),                 # segment count differs
    ("api/Employee/Edit", "api/Employee/Create", None),                        # literal mismatch
    ("", "api/x", None),
    ("{}", "{id}", "exact"),
])
def test_match(req, ep, want):
    assert routes.match(req, ep, CFG) == want


def test_case_sensitive_config_is_honoured():
    cs = {**CFG, "case_sensitive": True}
    assert routes.match("api/employee/index", "api/Employee/Index", cs) is None
    assert routes.match("api/Employee/Index", "api/Employee/Index", cs) == "exact"


def test_leading_slash_config_is_honoured():
    keep = {**CFG, "strip_leading_slash": False}
    assert routes.segments("/a/b", keep)[0] == ("lit", "")   # leading empty segment is kept


def test_segments_classify_params():
    assert routes.segments("a/{id}/b/{x:int}", CFG) == [("lit", "a"), ("param", None), ("lit", "b"), ("param", None)]


@pytest.mark.parametrize("rv,ev,ok", [("GET", "GET", True), ("GET", "POST", False), ("PUT", "ANY", True), ("PUT", None, True), ("DELETE", "", True)])
def test_verb_ok(rv, ev, ok):
    assert routes.verb_ok(rv, ev) is ok
