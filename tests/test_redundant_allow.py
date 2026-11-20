from robots_txt_lab.lint import INFO, lint
from robots_txt_lab.parser import parse


def redundant(text):
    return [(i.line, i.message) for i in lint(parse(text.encode("utf-8"))) if i.code == "redundant-allow"]


def test_allow_inside_disallowed_directory_is_needed():
    assert redundant("User-agent: *\nDisallow: /admin/\nAllow: /admin/public/\n") == []


def test_allow_without_any_disallow():
    found = redundant("User-agent: *\nAllow: /blog/\n")
    assert found == [(2, "allow: /blog/ has no effect for *: the group has no disallow rules")]


def test_allow_outside_every_disallow():
    found = redundant("User-agent: *\nDisallow: /cart\nAllow: /checkout/thanks\n")
    assert found == [(3, "allow: /checkout/thanks has no effect for *: no shorter disallow rule covers it")]


def test_longer_disallow_does_not_make_allow_useful():
    # /a/b/... is blocked by the longer disallow either way, /a/other is allowed by default.
    assert [line for line, _ in redundant("User-agent: *\nAllow: /a\nDisallow: /a/b\n")] == [2]


def test_same_length_conflict_is_left_to_conflicting_rules():
    issues = lint(parse(b"User-agent: *\nDisallow: /x\nAllow: /x\n"))
    codes = [i.code for i in issues]
    assert "conflicting-rules" in codes and "redundant-allow" not in codes


def test_wildcard_disallow_is_treated_as_overlapping():
    assert redundant("User-agent: *\nDisallow: /*.pdf\nAllow: /docs/\n") == []
    assert redundant("User-agent: *\nDisallow: /*?\nAllow: /search\n") == []


def test_wildcard_and_root_allows_are_not_reported():
    assert redundant("User-agent: *\nAllow: /\n") == []
    assert redundant("User-agent: *\nAllow: /*.css$\nAllow: /*.js\n") == []
    assert redundant("User-agent: *\nAllow: /exact$\n") == []


def test_groups_for_the_same_agent_are_merged():
    text = "User-agent: Googlebot\nDisallow: /private/\n\nUser-agent: googlebot\nAllow: /private/press/\n"
    assert redundant(text) == []


def test_other_agents_rules_do_not_count():
    text = "User-agent: Bingbot\nDisallow: /private/\n\nUser-agent: Googlebot\nAllow: /private/press/\n"
    assert [line for line, _ in redundant(text)] == [5]


def test_severity_and_suppression():
    issues = [i for i in lint(parse(b"User-agent: *\nAllow: /x\n")) if i.code == "redundant-allow"]
    assert issues[0].severity == INFO
    suppressed = b"User-agent: *\nAllow: /x  # robots-txt-lab: disable=redundant-allow\n"
    assert all(i.code != "redundant-allow" for i in lint(parse(suppressed)))
