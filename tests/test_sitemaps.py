from robots_txt_lab.parser import parse
from robots_txt_lab.sitemaps import sitemap_problems


def kinds(text, robots_url=None):
    return [p.kind for p in sitemap_problems(parse(text), robots_url)]


def test_valid_sitemaps_have_no_problems():
    text = "Sitemap: https://example.com/sitemap.xml\nsitemap: https://example.com/news.xml\n"
    assert kinds(text, "https://example.com/robots.txt") == []


def test_relative_url():
    assert kinds("Sitemap: /sitemap.xml\n") == ["sitemap-not-absolute"]
    assert kinds("Sitemap: example.com/sitemap.xml\n") == ["sitemap-not-absolute"]


def test_bad_scheme():
    assert kinds("Sitemap: ftp://example.com/s.xml\n") == ["sitemap-bad-scheme"]


def test_whitespace_and_empty():
    assert kinds("Sitemap: https://example.com/my sitemap.xml\n") == ["sitemap-invalid-url"]
    assert kinds("Sitemap:\n") == ["sitemap-empty"]


def test_hash_cuts_the_url():
    r = parse("Sitemap: https://example.com/s.xml#top\n")
    assert r.sitemap_urls == ["https://example.com/s.xml"]
    assert kinds("Sitemap: https://example.com/s.xml#top\n") == ["sitemap-hash"]
    assert kinds("Sitemap: https://example.com/s.xml # main sitemap\n") == []


def test_duplicate_is_reported_once():
    text = "Sitemap: https://example.com/s.xml\nSitemap: https://example.com/s.xml\n"
    problems = sitemap_problems(parse(text))
    assert [(p.kind, p.line) for p in problems] == [("sitemap-duplicate", 2)]


def test_cross_host_and_scheme_mismatch():
    assert kinds("Sitemap: https://cdn.example.org/s.xml\n", "https://example.com/robots.txt") == ["sitemap-cross-host"]
    assert kinds("Sitemap: http://example.com/s.xml\n", "https://example.com/robots.txt") == ["sitemap-scheme-mismatch"]
    assert kinds("Sitemap: https://cdn.example.org/s.xml\n") == []


def test_unicode_sitemap_urls_are_fine():
    assert kinds("sitemap: https://ja.example.org/テスト-サイトマップ.xml\n") == []
