"""Google's "Examples of valid robots.txt URLs" table."""

import pytest

from robots_txt_lab.scope import ScopeError, in_scope, is_valid_robots_location, origin_of, robots_url

TABLE = [
    (
        "https://example.com/robots.txt",
        ["https://example.com/", "https://example.com/folder/file"],
        ["https://other.example.com/", "http://example.com/", "https://example.com:8181/"],
    ),
    (
        "https://www.example.com/robots.txt",
        ["https://www.example.com/"],
        ["https://example.com/", "https://shop.www.example.com/", "https://www.shop.example.com/"],
    ),
    (
        "https://www.exämple.com/robots.txt",
        ["https://www.exämple.com/", "https://www.xn--exmple-cua.com/"],
        ["https://www.example.com/"],
    ),
    ("ftp://example.com/robots.txt", ["ftp://example.com/"], ["https://example.com/"]),
    ("https://212.96.82.21/robots.txt", ["https://212.96.82.21/"], ["https://example.com/"]),
    (
        "https://example.com:443/robots.txt",
        ["https://example.com:443/", "https://example.com/"],
        ["https://example.com:444/"],
    ),
    ("https://example.com:8181/robots.txt", ["https://example.com:8181/"], ["https://example.com/"]),
]


@pytest.mark.parametrize(("robots", "yes", "no"), TABLE)
def test_google_validity_table(robots, yes, no):
    for url in yes:
        assert in_scope(robots, url), url
    for url in no:
        assert not in_scope(robots, url), url


def test_idn_is_converted_to_punycode():
    # The Google table writes the punycode as xn--exmple-cua.com; this is the IDNA form of exämple.com.
    assert robots_url("https://www.exämple.com/page") == "https://www.xn--exmple-cua.com/robots.txt"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://Example.COM/a/b?c#d", "https://example.com/robots.txt"),
        ("http://example.com:80/", "http://example.com/robots.txt"),
        ("https://example.com:8443/x", "https://example.com:8443/robots.txt"),
        ("https://example.com./x", "https://example.com/robots.txt"),
        ("http://[2001:db8::1]:8080/x", "http://[2001:db8::1]:8080/robots.txt"),
    ],
)
def test_robots_url(url, expected):
    assert robots_url(url) == expected


def test_subdirectory_robots_txt_is_not_valid():
    assert is_valid_robots_location("https://example.com/robots.txt")
    assert not is_valid_robots_location("https://example.com/folder/robots.txt")
    assert not is_valid_robots_location("example.com/robots.txt")


def test_origin_errors():
    with pytest.raises(ScopeError):
        origin_of("/just/a/path")
    with pytest.raises(ScopeError):
        origin_of("https://example.com:99999/")
    assert not in_scope("not a url", "https://example.com/")
