"""Examples from RFC 9309 (https://www.rfc-editor.org/rfc/rfc9309)."""

import pytest

from .conftest import robots

# Section 5.1 expected outcomes
SIMPLE = [
    # The "*" group: any agent without its own group.
    ("otherbot", "/publications/", True),
    ("otherbot", "/publications/2024.html", True),
    ("otherbot", "/example/", False),
    ("otherbot", "/example/page.html", False),
    ("otherbot", "/image.gif", False),
    ("otherbot", "/images/a/b.gif", False),
    # "Allow: /publications/" (14 octets) is longer than "Disallow: *.gif$" (6), so it wins.
    ("otherbot", "/publications/cover.gif", True),
    ("otherbot", "/image.gif?v=2", True),
    ("otherbot", "/other/page.html", True),
    # foobot: only /example/page.html and /example/allowed.gif.
    ("foobot", "/example/page.html", True),
    ("foobot", "/example/allowed.gif", True),
    ("foobot", "/example/other.html", False),
    ("foobot", "/", False),
    ("foobot", "/publications/", False),
    # barbot and bazbot share a group.
    ("barbot", "/example/page.html", False),
    ("bazbot", "/example/page.html", False),
    ("barbot", "/example/page.html.bak", False),
    ("barbot", "/example/other.html", True),
    ("bazbot", "/image.gif", True),
    # quxbot: empty group at the end of the file, unrestricted.
    ("quxbot", "/example/page.html", True),
    ("quxbot", "/image.gif", True),
    ("quxbot", "/", True),
]


@pytest.mark.parametrize(("agent", "path", "expected"), SIMPLE)
def test_section_5_1_simple_example(rfc_simple, agent, path, expected):
    assert robots(rfc_simple).allowed(f"https://example.com{path}", agent) is expected


@pytest.mark.parametrize("profile", ["google", "rfc"])
def test_section_5_1_same_in_both_profiles(rfc_simple, profile):
    r = robots(rfc_simple, profile)
    assert [r.allowed(p, a) for a, p, _ in SIMPLE] == [e for _, _, e in SIMPLE]


def test_section_5_1_agents_are_case_insensitive(rfc_simple):
    r = robots(rfc_simple)
    assert r.allowed("/example/page.html", "FooBot")
    assert not r.allowed("/example/page.html", "BAZBOT")


def test_section_5_2_longest_match():
    # "/example/page/disallowed.gif MUST be used" for that URI.
    r = robots("User-Agent: foobot\nAllow: /example/page/\nDisallow: /example/page/disallowed.gif\n")
    v = r.check("https://example.com/example/page/disallowed.gif", "foobot")
    assert not v.allowed
    assert v.rule.path == "/example/page/disallowed.gif"
    assert r.allowed("https://example.com/example/page/other.gif", "foobot")
    # As printed, the RFC's URI ends in "disallow.gif", which only the allow rule matches.
    assert r.allowed("https://example.com/example/page/disallow.gif", "foobot")


def test_figure_2_groups_for_the_same_token_are_merged():
    r = robots("user-agent: ExampleBot\ndisallow: /foo\ndisallow: /bar\n\nuser-agent: ExampleBot\ndisallow: /baz\n")
    for path in ("/foo", "/bar", "/baz"):
        assert not r.allowed(path, "ExampleBot")
    assert r.check("/baz", "ExampleBot").group_lines == (1, 5)


def test_figure_3_star_group_when_no_specific_group():
    r = robots("user-agent: *\ndisallow: /foo\ndisallow: /bar\n\nuser-agent: BazBot\ndisallow: /baz\n")
    assert not r.allowed("/foo", "ExampleBot")
    assert not r.allowed("/bar", "ExampleBot")
    assert r.allowed("/baz", "ExampleBot")
    assert r.check("/foo", "ExampleBot").group_token == "*"


def test_figure_1_product_token_from_user_agent_header():
    r = robots("user-agent: ExampleBot\ndisallow: /private\n")
    ua = "Mozilla/5.0 (compatible; ExampleBot/0.1; https://www.example.com/bot.html)"
    assert not r.allowed("/private", ua)


def test_no_matching_group_and_no_star_means_no_rules():
    r = robots("user-agent: a\ndisallow: /\n")
    v = r.check("/x", "b")
    assert v.allowed and v.reason == "no-matching-group"


def test_no_groups_at_all():
    assert robots("").allowed("/anything", "bot")
    assert robots("# only a comment\n").allowed("/", "bot")


def test_robots_txt_is_implicitly_allowed():
    r = robots("user-agent: *\ndisallow: /\n")
    v = r.check("https://example.com/robots.txt", "bot")
    assert v.allowed and v.reason == "robots-txt-always-allowed"
    assert not r.allowed("https://example.com/robots.txt.bak", "bot")


def test_rules_outside_groups_are_ignored():
    r = robots("disallow: /\nuser-agent: *\ndisallow: /x\n")
    assert r.allowed("/y", "bot")


def test_comments_per_section_2_2_3():
    r = robots("user-agent: *\nallow: / # comment in line\n# comment on its own line\ndisallow: /x # no\n")
    assert r.allowed("/y", "bot")
    assert not r.allowed("/x", "bot")


def test_sitemaps_record_does_not_terminate_a_group():
    # Section 2.2.4: a "Sitemaps" record MUST NOT terminate a group.
    r = robots("user-agent: a\nsitemap: https://example.com/s.xml\nuser-agent: b\ndisallow: /\n")
    assert not r.allowed("/x", "a")
    assert not r.allowed("/x", "b")


def test_percent_encoded_unreserved_in_uri_matches_rule():
    r = robots("user-agent: *\ndisallow: /foo/bar/baz\n")
    assert not r.allowed("https://example.com/foo/bar/%62%61%7A", "bot")


def test_non_ascii_rule_matches_encoded_uri():
    r = robots("user-agent: *\ndisallow: /foo/bar/ツ\n")
    assert not r.allowed("https://example.com/foo/bar/%E3%83%84", "bot")
    assert not r.allowed("https://example.com/foo/bar/ツ", "bot")
