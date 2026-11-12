import pytest

from robots_txt_lab.parser import MAX_BYTES, parse, parse_file


def kinds(robots):
    return [n.kind for n in robots.notes]


def test_simple_group():
    r = parse("User-agent: *\nDisallow: /private/\nAllow: /private/public\n")
    assert len(r.groups) == 1
    g = r.groups[0]
    assert g.tokens == ["*"]
    assert [(x.allow, x.path, x.line) for x in g.rules] == [(False, "/private/", 2), (True, "/private/public", 3)]
    assert g.is_global


@pytest.mark.parametrize("sep", ["\n", "\r\n", "\r"])
def test_line_endings(sep):
    r = parse(sep.join(["User-agent: a", "Disallow: /x", "User-agent: b", "Disallow: /y"]) + sep)
    assert [g.tokens for g in r.groups] == [["a"], ["b"]]
    assert r.groups[1].rules[0].line == 4


def test_mixed_line_endings():
    r = parse("User-agent: a\r\nDisallow: /x\rDisallow: /y\nDisallow: /z")
    assert [x.path for x in r.groups[0].rules] == ["/x", "/y", "/z"]


def test_comments_and_whitespace():
    r = parse("  # header\nUser-agent : *   # all\n\tDisallow :\t/a b # trailing\n# Disallow: /no\n")
    assert r.groups[0].rules[0].path == "/a b"
    assert len(r.groups[0].rules) == 1


def test_field_names_are_case_insensitive():
    r = parse("USER-AGENT: X\nDISALLOW: /a\nallow: /a/b\nSiteMap: https://e.com/s.xml\n")
    assert r.groups[0].tokens == ["x"]
    assert len(r.groups[0].rules) == 2
    assert r.sitemap_urls == ["https://e.com/s.xml"]


def test_values_keep_case():
    assert parse("User-agent: *\nDisallow: /Fish\n").groups[0].rules[0].path == "/Fish"


def test_consecutive_user_agents_share_a_group():
    r = parse("User-agent: a\nUser-agent: b\nDisallow: /x\n")
    assert r.groups[0].tokens == ["a", "b"]


def test_blank_lines_do_not_end_a_group():
    r = parse("User-agent: a\n\nDisallow: /x\n\n\nAllow: /y\n")
    assert len(r.groups) == 1
    assert len(r.groups[0].rules) == 2


def test_blank_line_between_user_agents_keeps_one_group():
    r = parse("User-agent: a\n\nUser-agent: b\nDisallow: /\n")
    assert r.groups[0].tokens == ["a", "b"]


def test_user_agent_after_rule_starts_new_group():
    r = parse("User-agent: a\nDisallow: /x\nUser-agent: b\nDisallow: /y\n")
    assert [g.tokens for g in r.groups] == [["a"], ["b"]]


def test_sitemap_and_unknown_lines_do_not_end_a_group():
    # Google: "user-agent: a / sitemap: ... / user-agent: b / disallow: /" is one group.
    r = parse("user-agent: a\nsitemap: https://example.com/sitemap.xml\n\nuser-agent: b\ndisallow: /\n")
    assert len(r.groups) == 1
    assert r.groups[0].tokens == ["a", "b"]
    r2 = parse("user-agent: a\ncrawl-delay: 5\nuser-agent: b\ndisallow: /\n")
    assert r2.groups[0].tokens == ["a", "b"]


def test_rules_before_any_user_agent_are_ignored():
    r = parse("Disallow: /x\nUser-agent: *\nDisallow: /y\n")
    assert [x.path for x in r.groups[0].rules] == ["/y"]
    assert "rule-outside-group" in kinds(r)


def test_empty_values_are_ignored_but_recorded():
    r = parse("User-agent: *\nDisallow:\nAllow:   \n")
    assert r.groups[0].rules == []
    assert r.groups[0].empty_rules == [2, 3]


def test_empty_disallow_still_ends_user_agent_run():
    r = parse("User-agent: a\nDisallow:\nUser-agent: b\nDisallow: /\n")
    assert [g.tokens for g in r.groups] == [["a"], ["b"]]


def test_group_with_no_rules_at_end_of_file():
    r = parse("User-agent: a\nDisallow: /x\n\nUser-agent: quxbot\n")
    assert r.groups[1].tokens == ["quxbot"]
    assert r.groups[1].rules == []


def test_other_directives_are_collected_with_group():
    r = parse("Crawl-delay: 1\nUser-agent: *\nCrawl-delay: 10\nHost: example.com\n")
    assert [(d.key, d.value, d.group) for d in r.others] == [
        ("crawl-delay", "1", None),
        ("crawl-delay", "10", 0),
        ("host", "example.com", 0),
    ]


def test_value_may_contain_colons():
    r = parse("Sitemap: https://example.com:8443/s.xml\nUser-agent: *\nDisallow: /a:b\n")
    assert r.sitemap_urls == ["https://example.com:8443/s.xml"]
    assert r.groups[0].rules[0].path == "/a:b"


@pytest.mark.parametrize(
    ("key", "canonical"),
    [
        ("useragent", "user-agent"),
        ("user agent", "user-agent"),
        ("dissallow", "disallow"),
        ("dissalow", "disallow"),
        ("disalow", "disallow"),
        ("diasllow", "disallow"),
        ("disallaw", "disallow"),
    ],
)
def test_google_accepts_typos(key, canonical):
    text = f"user-agent: *\n{key}: /x\n" if canonical == "disallow" else f"{key}: bot\ndisallow: /x\n"
    r = parse(text)
    assert len(r.groups[0].rules) == 1
    assert "typo" in kinds(r)


def test_site_map_typo():
    r = parse("site-map: https://example.com/s.xml\n")
    assert r.sitemap_urls == ["https://example.com/s.xml"]


def test_rfc_profile_rejects_typos():
    r = parse("user-agent: *\ndissallow: /x\n", profile="rfc")
    assert r.groups[0].rules == []
    assert [d.key for d in r.others] == ["dissallow"]


def test_missing_colon_google_only():
    g = parse("user-agent *\ndisallow /x\n")
    assert g.groups[0].rules[0].path == "/x"
    assert kinds(g).count("missing-colon") == 2
    r = parse("user-agent *\ndisallow /x\n", profile="rfc")
    assert r.groups == []
    assert kinds(r).count("invalid-line") == 2


def test_invalid_lines():
    r = parse("User-agent: *\n<html>\nEOF\njust some words here\n")
    assert kinds(r).count("invalid-line") == 3


def test_html_page_with_rules_is_still_parsed():
    r = parse("<html><body>\nUser-agent: *\nDisallow: /x\n</body></html>\n")
    assert r.groups[0].rules[0].path == "/x"


def test_bom_is_ignored():
    r = parse(b"\xef\xbb\xbfUser-agent: *\nDisallow: /x\n")
    assert r.had_bom
    assert r.groups[0].tokens == ["*"]
    r2 = parse("﻿User-agent: *\nDisallow: /x\n")
    assert r2.had_bom and r2.groups[0].tokens == ["*"]


def test_size_limit_ignores_content_after_500_kib():
    head = b"User-agent: *\nDisallow: /early\n"
    filler = b"# " + b"x" * (MAX_BYTES) + b"\n"
    r = parse(head + filler + b"Disallow: /late\n")
    assert r.truncated
    assert [x.path for x in r.groups[0].rules] == ["/early"]
    assert r.size_bytes > MAX_BYTES


def test_exactly_at_the_limit_is_not_truncated():
    body = b"User-agent: *\nDisallow: /x\n"
    r = parse(body + b"#" * (MAX_BYTES - len(body)))
    assert not r.truncated


def test_custom_size_limit():
    r = parse("User-agent: *\nDisallow: /a\nDisallow: /b\n", max_bytes=27)
    assert [x.path for x in r.groups[0].rules] == ["/a"]


def test_invalid_utf8_is_replaced():
    r = parse(b"User-agent: *\nDisallow: /caf\xe9\n")
    assert r.decode_errors
    assert r.groups[0].rules[0].pattern == "/caf%EF%BF%BD"


def test_rules_are_normalised():
    r = parse("User-agent: *\nDisallow: /foo/bar/ツ\nDisallow: /%7euser\n")
    assert [x.pattern for x in r.groups[0].rules] == ["/foo/bar/%E3%83%84", "/~user"]


def test_user_agent_tokens():
    r = parse("User-agent: Googlebot/2.1\nUser-agent: googlebot*\nUser-agent: Mozilla/5.0 (X)\nUser-agent: /\n")
    g = r.groups[0]
    assert g.tokens == ["googlebot", "googlebot", "mozilla"]
    assert "invalid-user-agent" in kinds(r)


def test_unknown_profile():
    with pytest.raises(ValueError):
        parse("", profile="bing")


def test_empty_file():
    r = parse("")
    assert r.groups == [] and r.lines == []


def test_parse_file(tmp_path):
    p = tmp_path / "robots.txt"
    p.write_bytes(b"User-agent: *\nDisallow: /x\n")
    assert parse_file(str(p)).groups[0].rules[0].path == "/x"


def test_lines_are_kept_for_reporting():
    r = parse("a\nb\n")
    assert r.lines == ["a", "b"]
