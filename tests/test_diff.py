from robots_txt_lab.diff import derive_test_urls, diff

from .conftest import robots

OLD = "User-agent: *\nDisallow: /admin/\nDisallow: /tmp/\nSitemap: https://example.com/old.xml\n"
NEW = (
    "User-agent: *\nDisallow: /admin/\nDisallow: /search\n\nUser-agent: Googlebot\nDisallow: /beta/\n"
    "Sitemap: https://example.com/new.xml\n"
)


def test_rule_changes():
    result = diff(robots(OLD), robots(NEW), ["/x"])
    got = {(c.agents, c.change, c.directive, c.path) for c in result.rule_changes}
    assert got == {
        ("*", "removed", "disallow", "/tmp/"),
        ("*", "added", "disallow", "/search"),
        ("googlebot", "added", "disallow", "/beta/"),
    }
    assert result.changed


def test_sitemap_changes():
    result = diff(robots(OLD), robots(NEW), ["/x"])
    assert result.sitemaps_added == ["https://example.com/new.xml"]
    assert result.sitemaps_removed == ["https://example.com/old.xml"]


def test_verdict_changes_for_given_urls():
    urls = ["https://example.com/tmp/a", "https://example.com/search?q=x", "https://example.com/admin/", "/tmp/b"]
    result = diff(robots(OLD), robots(NEW), urls, ["Googlebot", "Bingbot"])
    changes = {(c.url, c.user_agent, c.direction) for c in result.verdict_changes}
    # A new Googlebot group means Googlebot no longer follows the "*" rules at all.
    assert ("https://example.com/tmp/a", "Bingbot", "now-allowed") in changes
    assert ("https://example.com/search?q=x", "Bingbot", "now-disallowed") in changes
    assert ("https://example.com/admin/", "Googlebot", "now-allowed") in changes
    assert ("https://example.com/admin/", "Bingbot", "now-allowed") not in changes
    assert not result.derived_urls


def test_identical_files_have_no_changes():
    result = diff(robots(OLD), robots(OLD), ["/tmp/a"])
    assert not result.changed
    assert result.verdict_changes == []


def test_reordering_and_formatting_is_not_a_change():
    a = "User-agent: *\nDisallow: /a\nDisallow: /b\n"
    b = "user-agent:*\n\ndisallow:/b # comment\nDISALLOW: /a\n"
    assert not diff(robots(a), robots(b), ["/a", "/b"]).changed


def test_equivalent_encodings_are_not_a_change():
    a = "User-agent: *\nDisallow: /foo/bar/ツ\n"
    b = "User-agent: *\nDisallow: /foo/bar/%E3%83%84\n"
    assert diff(robots(a), robots(b), ["/x"]).rule_changes == []


def test_urls_are_derived_when_none_given():
    result = diff(robots(OLD), robots(NEW))
    assert result.derived_urls
    assert "/tmp/" in result.urls_tested and "/search" in result.urls_tested
    assert any(c.url == "/tmp/page" for c in result.verdict_changes)


def test_derive_test_urls_for_wildcards():
    urls = derive_test_urls(robots("User-agent: *\nDisallow: /*.pdf$\nDisallow: /a/*/b\n").parsed)
    assert "/x.pdf" in urls
    assert "/a/" in urls
    assert "/" in urls


def test_to_dict():
    d = diff(robots(OLD), robots(NEW), ["/tmp/a"]).to_dict()
    assert d["changed"] is True
    assert d["verdict_changes"][0]["before"]["allowed"] is False
    assert d["urls_tested"] == 1


def test_access_state_changes_are_verdict_changes():
    from robots_txt_lab import Robots

    result = diff(robots(OLD), Robots.disallow_all("HTTP 503"), ["/public"], ["Googlebot"])
    assert result.verdict_changes[0].after.reason == "unreachable-disallow-all"
