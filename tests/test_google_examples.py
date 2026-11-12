"""Examples from Google's "How Google interprets the robots.txt specification"."""

import pytest

from .conftest import robots

INTRO = """# This robots.txt file controls crawling of URLs under https://example.com.
# All crawlers are disallowed to crawl files in the "includes" directory, such
# as .css, .js, but Google needs them for rendering, so Googlebot is allowed
# to crawl them.
User-agent: *
Disallow: /includes/

User-agent: Googlebot
Allow: /includes/

Sitemap: https://example.com/sitemap.xml
"""


def test_intro_example():
    r = robots(INTRO)
    assert r.allowed("https://example.com/includes/app.js", "Googlebot")
    assert not r.allowed("https://example.com/includes/app.js", "Bingbot")
    assert r.sitemaps == ["https://example.com/sitemap.xml"]


USER_AGENT_PRECEDENCE = """user-agent: googlebot-news
disallow: /group1

user-agent: *
disallow: /group2

user-agent: googlebot
disallow: /group3
"""


@pytest.mark.parametrize(
    ("agent", "group_path"),
    [
        ("Googlebot-News", "/group1"),
        ("Googlebot", "/group3"),
        ("Storebot-Google", "/group2"),
        ("Otherbot", "/group2"),
    ],
)
def test_order_of_precedence_for_user_agents(agent, group_path):
    r = robots(USER_AGENT_PRECEDENCE)
    for path in ("/group1", "/group2", "/group3"):
        assert r.allowed(path, agent) is (path != group_path), (agent, path)


def test_group_order_is_irrelevant():
    reordered = "user-agent: googlebot\ndisallow: /g\n\nuser-agent: *\ndisallow: /s\n"
    assert not robots(reordered).allowed("/g", "Googlebot")
    assert robots(reordered).allowed("/s", "Googlebot")


def test_specific_and_global_groups_are_not_combined():
    r = robots("user-agent: *\ndisallow: /carrots\n\nuser-agent: googlebot\ndisallow: /fish\n")
    assert r.allowed("/carrots", "Googlebot")


def test_grouping_of_rules_merges_specific_groups():
    r = robots(
        "user-agent: googlebot-news\ndisallow: /fish\n\nuser-agent: *\ndisallow: /carrots\n\n"
        "user-agent: googlebot-news\ndisallow: /shrimp\n"
    )
    assert not r.allowed("/fish", "googlebot-news")
    assert not r.allowed("/shrimp", "googlebot-news")
    assert r.allowed("/carrots", "googlebot-news")
    assert not r.allowed("/carrots", "otherbot")


def test_sitemap_between_user_agents_is_one_group():
    r = robots("user-agent: a\nsitemap: https://example.com/sitemap.xml\n\nuser-agent: b\ndisallow: /\n")
    assert not r.allowed("/page", "a")
    assert not r.allowed("/page", "b")
    assert r.sitemaps == ["https://example.com/sitemap.xml"]


def test_four_distinct_groups():
    text = (
        "user-agent: a\ndisallow: /c\n\nuser-agent: b\ndisallow: /d\n\n"
        "user-agent: e\nuser-agent: f\ndisallow: /g\n\nuser-agent: h\n"
    )
    r = robots(text)
    assert len(r.parsed.groups) == 4
    assert not r.allowed("/c", "a") and r.allowed("/d", "a")
    assert not r.allowed("/d", "b")
    assert not r.allowed("/g", "e") and not r.allowed("/g", "f")
    assert r.allowed("/c", "h") and r.allowed("/g", "h")


def test_user_agent_values_ignore_non_token_text():
    for value in ("googlebot/1.2", "googlebot*", "Googlebot"):
        r = robots(f"user-agent: {value}\ndisallow: /x\n")
        assert not r.allowed("/x", "Googlebot"), value


@pytest.mark.parametrize(
    ("url", "rules", "expected_rule", "allowed"),
    [
        ("https://example.com/page", "allow: /p\ndisallow: /", "allow: /p", True),
        ("https://example.com/folder/page", "allow: /folder\ndisallow: /folder", "allow: /folder", True),
        ("https://example.com/page.htm", "allow: /page\ndisallow: /*.htm", "disallow: /*.htm", False),
        ("https://example.com/page.php5", "allow: /page\ndisallow: /*.ph", "allow: /page", True),
        ("https://example.com/", "allow: /$\ndisallow: /", "allow: /$", True),
        ("https://example.com/page.htm", "allow: /$\ndisallow: /", "disallow: /", False),
    ],
)
def test_order_of_precedence_for_rules(url, rules, expected_rule, allowed):
    v = robots(f"user-agent: *\n{rules}\n").check(url, "Googlebot")
    assert str(v.rule) == expected_rule
    assert v.allowed is allowed


def test_multiple_sitemaps_including_other_hosts_and_unicode():
    r = robots(
        "user-agent: otherbot\ndisallow: /kale\n\nsitemap: https://example.com/sitemap.xml\n"
        "sitemap: https://cdn.example.org/other-sitemap.xml\n"
        "sitemap: https://ja.example.org/テスト-サイトマップ.xml\n"
    )
    assert len(r.sitemaps) == 3
    assert r.sitemaps[2].endswith("プ.xml")


def test_rules_without_a_path_are_ignored():
    r = robots("user-agent: *\ndisallow:\n")
    assert r.allowed("/anything", "Googlebot")


def test_google_crawler_fallback_tokens():
    r = robots("user-agent: googlebot\ndisallow: /photos/\n")
    assert not r.allowed("/photos/a.jpg", "Googlebot-Image")
    assert r.allowed("/photos/a.jpg", "Storebot-Google")
    specific = robots("user-agent: googlebot\ndisallow: /photos/\n\nuser-agent: googlebot-image\ndisallow: /raw/\n")
    assert specific.allowed("/photos/a.jpg", "Googlebot-Image")
    assert not specific.allowed("/raw/a.jpg", "Googlebot-Image")


def test_fallbacks_are_not_used_in_rfc_profile():
    r = robots("user-agent: googlebot\ndisallow: /photos/\n", profile="rfc")
    assert r.allowed("/photos/a.jpg", "Googlebot-Image")


def test_adsbot_ignores_the_global_group():
    r = robots("user-agent: *\ndisallow: /\n")
    v = r.check("/landing", "AdsBot-Google")
    assert v.allowed and v.reason == "no-matching-group"
    assert not robots("user-agent: *\ndisallow: /\n", profile="rfc").allowed("/landing", "AdsBot-Google")
    assert not robots("user-agent: adsbot-google\ndisallow: /\n").allowed("/landing", "AdsBot-Google")
