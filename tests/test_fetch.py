import pytest

from robots_txt_lab.fetch import (
    DEFAULT_USER_AGENT,
    OUTCOME_OK,
    OUTCOME_UNAVAILABLE,
    OUTCOME_UNREACHABLE,
    classify_status,
    fetch,
)
from robots_txt_lab.parser import MAX_BYTES

from .conftest import FakeTransport

ROBOTS = "https://example.com/robots.txt"
BODY = b"User-agent: *\nDisallow: /private/\nSitemap: https://example.com/sitemap.xml\n"


def test_200_is_parsed():
    t = FakeTransport({ROBOTS: (200, {"Content-Type": "text/plain"}, BODY)})
    r = fetch("https://example.com/some/page", transport=t)
    assert r.outcome == OUTCOME_OK
    assert r.status == 200
    assert r.robots.access == "parsed"
    assert not r.robots.allowed("https://example.com/private/x", "Googlebot")
    assert r.robots.sitemaps == ["https://example.com/sitemap.xml"]
    assert t.requests[0][0] == ROBOTS
    assert t.requests[0][1]["User-Agent"] == DEFAULT_USER_AGENT
    assert r.to_dict()["content_type"] == "text/plain"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 451])
def test_4xx_means_no_restrictions(status):
    r = fetch(ROBOTS, transport=FakeTransport({ROBOTS: (status, {}, b"User-agent: *\nDisallow: /\n")}))
    assert r.outcome == OUTCOME_UNAVAILABLE
    assert r.robots.access == "allow-all"
    v = r.robots.check("https://example.com/anything", "Googlebot")
    assert v.allowed and v.reason == "unavailable-allow-all"
    assert r.body == b""


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_5xx_means_complete_disallow(status):
    r = fetch(ROBOTS, transport=FakeTransport({ROBOTS: (status, {}, b"")}))
    assert r.outcome == OUTCOME_UNREACHABLE
    v = r.robots.check("https://example.com/", "Googlebot")
    assert not v.allowed and v.reason == "unreachable-disallow-all"


def test_429_google_is_a_server_error_but_rfc_is_unavailable():
    t = FakeTransport({ROBOTS: (429, {}, b"")})
    assert fetch(ROBOTS, transport=t).outcome == OUTCOME_UNREACHABLE
    assert fetch(ROBOTS, transport=t, profile="rfc").outcome == OUTCOME_UNAVAILABLE


def test_network_error_is_unreachable():
    r = fetch(ROBOTS, transport=FakeTransport({}, errors={ROBOTS: "timed out"}))
    assert r.outcome == OUTCOME_UNREACHABLE
    assert r.status is None
    assert "timed out" in r.reason
    assert r.chain == [(ROBOTS, None)]


def test_redirects_are_followed_across_hosts():
    t = FakeTransport(
        {
            ROBOTS: (301, {"Location": "https://www.example.com/robots.txt"}, b""),
            "https://www.example.com/robots.txt": (302, {"Location": "/real-robots.txt"}, b""),
            "https://www.example.com/real-robots.txt": (200, {}, BODY),
        }
    )
    r = fetch(ROBOTS, transport=t)
    assert r.outcome == OUTCOME_OK
    assert r.redirects == 2
    assert r.final_url == "https://www.example.com/real-robots.txt"
    # The rules found apply to the original host.
    assert not r.robots.allowed("https://example.com/private/a", "Googlebot")


def chain(n: int, final=(200, {}, BODY)):
    routes = {}
    for i in range(n):
        src = ROBOTS if i == 0 else f"https://example.com/r{i}"
        routes[src] = (301, {"Location": f"https://example.com/r{i + 1}"}, b"")
    routes[ROBOTS if n == 0 else f"https://example.com/r{n}"] = final
    return FakeTransport(routes)


def test_five_redirects_are_followed():
    r = fetch(ROBOTS, transport=chain(5))
    assert r.outcome == OUTCOME_OK
    assert r.redirects == 5


def test_more_than_five_redirects_is_unavailable():
    r = fetch(ROBOTS, transport=chain(6))
    assert r.outcome == OUTCOME_UNAVAILABLE
    assert "more than 5 redirects" in r.reason
    assert r.robots.allowed("https://example.com/private/", "Googlebot")
    assert len(r.chain) == 6


def test_custom_redirect_limit():
    assert fetch(ROBOTS, transport=chain(2), max_redirects=1).outcome == OUTCOME_UNAVAILABLE


def test_redirect_without_location():
    r = fetch(ROBOTS, transport=FakeTransport({ROBOTS: (302, {}, b"")}))
    assert r.outcome == OUTCOME_UNAVAILABLE
    assert "Location" in r.reason


def test_redirect_to_an_error():
    t = FakeTransport(
        {ROBOTS: (301, {"Location": "https://example.com/gone"}, b""), "https://example.com/gone": (503, {}, b"")}
    )
    assert fetch(ROBOTS, transport=t).outcome == OUTCOME_UNREACHABLE


def test_body_over_500_kib_is_truncated():
    big = BODY + b"#" * (MAX_BYTES + 10) + b"\nDisallow: /late\n"
    r = fetch(ROBOTS, transport=FakeTransport({ROBOTS: (200, {}, big)}))
    assert r.robots.parsed.truncated
    assert r.robots.allowed("https://example.com/late", "Googlebot")


def test_html_body_with_200_is_parsed_leniently():
    html = b"<!doctype html><html><body>Not found</body></html>"
    r = fetch(ROBOTS, transport=FakeTransport({ROBOTS: (200, {"content-type": "text/html"}, html)}))
    assert r.outcome == OUTCOME_OK
    assert r.robots.allowed("https://example.com/x", "Googlebot")


def test_custom_user_agent_header():
    t = FakeTransport({ROBOTS: (200, {}, BODY)})
    fetch(ROBOTS, transport=t, user_agent="MyBot/1.0")
    assert t.requests[0][1]["User-Agent"] == "MyBot/1.0"


@pytest.mark.parametrize(
    ("status", "google", "rfc"),
    [
        (200, "ok", "ok"),
        (204, "ok", "ok"),
        (404, "unavailable", "unavailable"),
        (429, "unreachable", "unavailable"),
        (500, "unreachable", "unreachable"),
        (100, "unreachable", "unreachable"),
    ],
)
def test_classify_status(status, google, rfc):
    assert classify_status(status, "google") == google
    assert classify_status(status, "rfc") == rfc


def test_to_dict():
    r = fetch(ROBOTS, transport=FakeTransport({ROBOTS: (200, {}, BODY)}))
    d = r.to_dict()
    assert d["outcome"] == "ok" and d["groups"] == 1 and d["redirects"] == 0
    assert d["chain"] == [{"url": ROBOTS, "status": 200}]
