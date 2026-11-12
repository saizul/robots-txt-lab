import robots_txt_lab
from robots_txt_lab import Robots, Verdict, parse


def test_public_api():
    for name in robots_txt_lab.__all__:
        assert hasattr(robots_txt_lab, name), name
    assert robots_txt_lab.__version__ == "0.1.0"


def test_verdict_details():
    r = Robots.from_text("User-agent: *\nDisallow: /private/\n")
    v = r.check("https://example.com/private/x?y=1", "Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert isinstance(v, Verdict)
    assert not v.allowed
    assert v.path == "/private/x?y=1"
    assert v.group_token == "*"
    assert v.rule.line == 2
    d = v.to_dict()
    assert d["rule"] == {"directive": "disallow", "path": "/private/", "line": 2}
    assert d["reason"] == "matched-disallow"


def test_check_many_and_rules_for():
    r = Robots.from_text("User-agent: a\nDisallow: /x\n\nUser-agent: *\nDisallow: /y\n")
    verdicts = r.check_many(["/x", "/y"], ["a", "b"])
    assert [v.allowed for v in verdicts] == [False, True, True, False]
    assert [str(x) for x in r.rules_for("a")] == ["disallow: /x"]


def test_allow_all_and_disallow_all():
    assert Robots.allow_all("HTTP 404").allowed("/x", "bot")
    assert not Robots.disallow_all("HTTP 503").allowed("/x", "bot")


def test_parse_is_exported():
    assert parse("User-agent: *\n").groups[0].is_global


def test_python_stdlib_disagreement_example():
    # urllib.robotparser uses first-match order; RFC 9309 uses the longest match.
    r = Robots.from_text("User-agent: *\nDisallow: /\nAllow: /public/\n")
    assert r.allowed("/public/page", "bot")
