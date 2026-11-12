import time

import pytest

from robots_txt_lab.encoding import normalize_pattern, request_path
from robots_txt_lab.matcher import best_rule, literal_prefix, pattern_matches
from robots_txt_lab.models import Rule


def matches(pattern: str, url: str) -> bool:
    return pattern_matches(normalize_pattern(pattern), request_path(url))


# Google: "URL matching based on path values" table
GOOGLE_TABLE = {
    "/": (["/", "/a", "/fish/salmon.html"], []),
    "/*": (["/", "/a", "/fish/salmon.html"], []),
    "/$": (["/"], ["/a", "/index.html"]),
    "/fish": (
        ["/fish", "/fish.html", "/fish/salmon.html", "/fishheads", "/fishheads/yummy.html", "/fish.php?id=anything"],
        ["/Fish.asp", "/catfish", "/?id=fish", "/desert/fish"],
    ),
    "/fish*": (
        ["/fish", "/fish.html", "/fish/salmon.html", "/fishheads", "/fishheads/yummy.html", "/fish.php?id=anything"],
        ["/Fish.asp", "/catfish", "/?id=fish", "/desert/fish"],
    ),
    "/fish/": (
        ["/fish/", "/fish/?id=anything", "/fish/salmon.htm"],
        ["/fish", "/fish.html", "/animals/fish/", "/Fish/Salmon.asp"],
    ),
    "/*.php": (
        [
            "/index.php",
            "/filename.php",
            "/folder/filename.php",
            "/folder/filename.php?parameters",
            "/folder/any.php.file.html",
            "/filename.php/",
        ],
        ["/", "/windows.PHP"],
    ),
    "/*.php$": (
        ["/filename.php", "/folder/filename.php"],
        ["/filename.php?parameters", "/filename.php/", "/filename.php5", "/windows.PHP"],
    ),
    "/fish*.php": (["/fish.php", "/fishheads/catfish.php?parameters"], ["/Fish.PHP"]),
}

CASES = [(p, u, True) for p, (yes, _) in GOOGLE_TABLE.items() for u in yes] + [
    (p, u, False) for p, (_, no) in GOOGLE_TABLE.items() for u in no
]


@pytest.mark.parametrize(("pattern", "url", "expected"), CASES)
def test_google_wildcard_table(pattern, url, expected):
    assert matches(pattern, url) is expected


# RFC 9309 section 2.2.3 examples
@pytest.mark.parametrize(
    ("pattern", "url", "expected"),
    [
        ("/this/path/exactly$", "/this/path/exactly", True),
        ("/this/path/exactly$", "/this/path/exactly/", False),
        ("/this/path/exactly$", "/this/path/exactly?x", False),
        ("/this/*/exactly", "/this/is/exactly", True),
        ("/this/*/exactly", "/this/a/b/exactly", True),
        ("/this/*/exactly", "/this//exactly", True),
        ("/this/*/exactly", "/this/exactly", False),
        # Figure 6: percent-encoded special characters match them literally.
        ("/path/file-with-a-%2A.html", "https://www.example.com/path/file-with-a-*.html", True),
        ("/path/file-with-a-%2A.html", "https://www.example.com/path/file-with-a-x.html", False),
        ("/path/foo-%24", "https://www.example.com/path/foo-$", True),
        ("/path/foo-%24", "https://www.example.com/path/foo-", False),
    ],
)
def test_rfc_special_characters(pattern, url, expected):
    assert matches(pattern, url) is expected


def test_matching_is_case_sensitive():
    assert matches("/Admin", "/Admin/x")
    assert not matches("/Admin", "/admin/x")


def test_star_matches_slash_and_empty():
    assert matches("*.gif$", "/a/b/c.gif")
    assert matches("/a*b", "/ab")


def test_dollar_in_the_middle_is_literal():
    assert matches("/a$b", "/a%24b")
    assert not matches("/a$b", "/ab")


def test_double_dollar_and_star_dollar():
    assert matches("/*$", "/anything")
    assert matches("/a$$", "/a%24")


def test_percent_encoded_rule_matches_raw_url():
    assert matches("/caf%C3%A9", "/café/menu")
    assert matches("/café", "/caf%c3%a9/menu")
    assert matches("/~user", "/%7Euser/page")


def test_encoded_slash_does_not_match_a_real_slash():
    assert not matches("/a/b", "/a%2Fb")


def test_no_catastrophic_backtracking():
    pattern = "/" + "*a" * 30 + "b"
    path = "/" + "a" * 3000
    start = time.perf_counter()
    assert not pattern_matches(pattern, path)
    assert time.perf_counter() - start < 2.0


def rule(allow: bool, path: str, line: int = 1) -> Rule:
    return Rule(allow, path, normalize_pattern(path), line)


def test_best_rule_longest_wins():
    rules = [rule(False, "/", 1), rule(True, "/p", 2)]
    assert best_rule(rules, "/page") == rules[1]


def test_best_rule_allow_wins_ties_in_any_order():
    a, d = rule(True, "/folder", 1), rule(False, "/folder", 2)
    assert best_rule([a, d], "/folder/page").allow
    assert best_rule([d, a], "/folder/page").allow


def test_best_rule_none_when_nothing_matches():
    assert best_rule([rule(False, "/x")], "/y") is None


def test_literal_prefix():
    assert literal_prefix("/a/*.php$") == "/a/"
    assert literal_prefix("/a$") == "/a"
    assert literal_prefix("/a$b") == "/a$b"
    assert literal_prefix("*.gif") == ""
