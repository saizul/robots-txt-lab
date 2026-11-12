import pytest

from robots_txt_lab.encoding import normalize_path, normalize_pattern, request_path, split_path_query


# RFC 9309 Figure 4: path, path to match
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/foo/bar?baz=quz", "/foo/bar?baz=quz"),
        ("/foo/bar/ツ", "/foo/bar/%E3%83%84"),
        ("/foo/bar/%E3%83%84", "/foo/bar/%E3%83%84"),
        ("/foo/bar/%62%61%7A", "/foo/bar/baz"),
    ],
)
def test_rfc_figure_4(path, expected):
    assert normalize_path(path) == expected
    assert normalize_pattern(path) == expected


def test_rfc_figure_4_encoded_reserved_query_stays_encoded():
    # Row 2: an already encoded reserved character keeps its escape.
    assert normalize_path("/foo/bar?baz=https%3A%2F%2Ffoo.bar") == "/foo/bar?baz=https%3A%2F%2Ffoo.bar"


def test_hex_digits_are_upper_cased():
    assert normalize_path("/a%2fb%e3%83%84") == "/a%2Fb%E3%83%84"


@pytest.mark.parametrize("ch", list("ABCxyz019-._~"))
def test_unreserved_escapes_are_decoded(ch):
    assert normalize_path(f"/%{ord(ch):02x}") == f"/{ch}"


@pytest.mark.parametrize("escape", ["%2F", "%3F", "%23", "%26", "%3D", "%2A", "%24", "%25", "%20"])
def test_reserved_and_special_escapes_are_kept(escape):
    assert normalize_path(f"/a{escape}b") == f"/a{escape}b"


def test_raw_utf8_rule_equals_encoded_rule():
    # Google: "Disallow: /foo/bar/ツ" and "Disallow: /foo/bar/%E3%83%84" are identical.
    assert normalize_pattern("/foo/bar/ツ") == normalize_pattern("/foo/bar/%E3%83%84")


def test_space_control_and_unsafe_ascii_are_encoded():
    assert normalize_path("/a b") == "/a%20b"
    assert normalize_path("/a\tb") == "/a%09b"
    assert normalize_path('/a"<>\\^`{|}') == "/a%22%3C%3E%5C%5E%60%7B%7C%7D"


def test_lone_percent_is_encoded():
    assert normalize_path("/100%") == "/100%25"
    assert normalize_path("/a%zz") == "/a%25zz"
    assert normalize_path("/a%4") == "/a%254"


def test_wildcards_are_literal_in_uris_and_special_in_patterns():
    assert normalize_path("/path/file-with-a-*.html") == "/path/file-with-a-%2A.html"
    assert normalize_path("/path/foo-$") == "/path/foo-%24"
    assert normalize_pattern("/path/*.html$") == "/path/*.html$"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com", "/"),
        ("https://example.com/", "/"),
        ("https://example.com/a/b.html", "/a/b.html"),
        ("https://example.com/a?b=1&c=2", "/a?b=1&c=2"),
        ("https://example.com/a?b=1#frag", "/a?b=1"),
        ("https://example.com/a#frag?x", "/a"),
        ("https://example.com/a?", "/a?"),
        ("https://example.com?q=1", "/?q=1"),
        ("https://user:pw@example.com:8080/x", "/x"),
        ("//example.com/x?y", "/x?y"),
        ("/fish.php?id=anything", "/fish.php?id=anything"),
        ("fish", "/fish"),
        ("", "/"),
        ("https://example.com/café", "/caf%C3%A9"),
        ("https://example.com/%7Euser/", "/~user/"),
    ],
)
def test_request_path(url, expected):
    assert request_path(url) == expected


def test_split_path_query():
    assert split_path_query("https://e.com/a?b") == ("/a", "b")
    assert split_path_query("https://e.com/a") == ("/a", None)
    assert split_path_query("https://e.com") == ("", None)
