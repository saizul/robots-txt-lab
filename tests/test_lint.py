import pytest

from robots_txt_lab.lint import ERROR, INFO, WARNING, at_or_above, lint, worst_severity
from robots_txt_lab.parser import MAX_BYTES, parse


def codes(text, **kw):
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    return [i.code for i in lint(parse(data, profile=kw.get("profile", "google")), **kw)]


def issue(text, code, **kw):
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    found = [i for i in lint(parse(data), **kw) if i.code == code]
    assert found, f"{code} not reported"
    return found[0]


CLEAN = """User-agent: *
Disallow: /admin/
Disallow: /cart
Allow: /admin/public/

Sitemap: https://example.com/sitemap.xml
"""


def test_clean_file_has_no_issues():
    assert codes(CLEAN, robots_url="https://example.com/robots.txt") == []


def test_bom():
    i = issue(b"\xef\xbb\xbfUser-agent: *\nDisallow: /x\n", "bom")
    assert i.severity == INFO and i.line == 1


def test_size_limit_and_near_limit():
    big = b"User-agent: *\nDisallow: /x\n" + b"#" * MAX_BYTES
    assert issue(big, "size-limit").severity == ERROR
    near = b"User-agent: *\nDisallow: /x\n" + b"#" * int(MAX_BYTES * 0.95)
    assert issue(near, "size-near-limit").severity == WARNING


def test_not_utf8():
    assert "not-utf8" in codes(b"User-agent: *\nDisallow: /caf\xe9\n")


def test_html_content():
    assert issue("<!DOCTYPE html>\n<html><head></head></html>\n", "html-content").severity == ERROR


def test_no_groups():
    assert codes("Sitemap: https://example.com/s.xml\n") == ["no-groups"]


@pytest.mark.parametrize(
    ("directive", "code", "severity"),
    [
        ("Crawl-delay: 10", "crawl-delay-ignored", WARNING),
        ("Noindex: /x", "noindex-unsupported", WARNING),
        ("Host: example.com", "host-directive", INFO),
        ("Clean-param: ref /", "clean-param-directive", INFO),
        ("Request-rate: 1/5", "nonstandard-directive", INFO),
        ("Foo: bar", "unknown-directive", WARNING),
    ],
)
def test_other_directives(directive, code, severity):
    i = issue(f"User-agent: *\nDisallow: /x\n{directive}\n", code)
    assert i.severity == severity and i.line == 3


def test_misspelled_and_missing_colon():
    assert issue("User-agent: *\nDissallow: /x\n", "misspelled-directive").line == 2
    assert issue("User-agent: *\nDisallow /x\n", "missing-colon").line == 2


def test_invalid_line():
    assert issue("User-agent: *\nthis is not a rule\n", "invalid-line").line == 2


def test_rule_outside_group():
    i = issue("Disallow: /x\nUser-agent: *\nDisallow: /y\n", "rule-outside-group")
    assert i.severity == ERROR and i.line == 1


def test_directive_case():
    assert issue("USER-AGENT: *\nDisallow: /x\n", "directive-case").line == 1
    assert "directive-case" not in codes("user-agent: *\ndisallow: /x\nUser-Agent: a\nDisallow: /y\n")


def test_user_agent_token_notes():
    assert "user-agent-token" in codes("User-agent: Googlebot/2.1\nDisallow: /x\n")
    assert "invalid-user-agent" in codes("User-agent: /weird\nDisallow: /x\n")
    assert "user-agent-token" not in codes("User-agent: Googlebot\nDisallow: /x\n")


def test_empty_group_and_empty_rule():
    assert issue("User-agent: a\nDisallow: /x\n\nUser-agent: quxbot\n", "empty-group").line == 4
    assert issue("User-agent: *\nDisallow:\n", "empty-rule").line == 2


def test_duplicate_and_conflicting_rules():
    text = "User-agent: *\nDisallow: /a\nDisallow: /a\nAllow: /a\n"
    assert issue(text, "duplicate-rule").line == 3
    assert issue(text, "conflicting-rules").line == 4


def test_path_without_leading_slash():
    assert issue("User-agent: *\nDisallow: private\n", "path-no-leading-slash").severity == WARNING
    assert "path-no-leading-slash" not in codes("User-agent: *\nDisallow: *.gif$\n")


def test_dollar_and_redundant_wildcard():
    assert "dollar-not-at-end" in codes("User-agent: *\nDisallow: /a$b\n")
    assert "dollar-not-at-end" not in codes("User-agent: *\nDisallow: /a$\n")
    assert "redundant-wildcard" in codes("User-agent: *\nDisallow: /fish*\n")


def test_disallow_robots_txt():
    assert "robots-txt-disallowed" in codes("User-agent: *\nDisallow: /robots.txt\n")


def test_path_case():
    i = issue("User-agent: *\nDisallow: /Admin/\n", "path-case")
    assert "/admin/" in i.message


def test_absolute_url_rule():
    assert issue("User-agent: *\nDisallow: https://example.com/x\n", "absolute-url-rule").severity == ERROR


@pytest.mark.parametrize("agent", ["*", "Googlebot"])
def test_blocks_entire_site_for_search_agents_is_an_error(agent):
    i = issue(f"User-agent: {agent}\nDisallow: /\n", "blocks-entire-site")
    assert i.severity == ERROR and i.line == 2


def test_blocks_entire_site_for_other_agents_is_a_warning():
    text = "User-agent: *\nDisallow: /x\n\nUser-agent: GPTBot\nDisallow: /\n"
    assert issue(text, "blocks-entire-site").severity == WARNING


def test_blocks_entire_site_with_allows_is_info():
    text = "User-agent: *\nDisallow: /\nAllow: /public/\n"
    assert issue(text, "blocks-entire-site").severity == INFO


@pytest.mark.parametrize(
    "rule",
    ["/wp-includes/", "/assets/", "/static/", "/*.css$", "/*.js", "/js/", "/css/", "/wp-content/plugins/"],
)
def test_blocks_css_and_js(rule):
    assert "blocks-resources" in codes(f"User-agent: *\nDisallow: {rule}\n")


def test_resources_allowed_back_are_not_reported():
    text = "User-agent: *\nDisallow: /assets/\nAllow: /assets/*.css$\nAllow: /assets/*.js$\n"
    assert "blocks-resources" not in codes(text)


def test_resources_blocked_only_in_the_global_group():
    text = "User-agent: *\nDisallow: /assets/\n\nUser-agent: Googlebot\nAllow: /\n"
    i = issue(text, "blocks-resources")
    assert "'*' group" in i.message


def test_resources_reported_once_per_rule():
    text = "User-agent: *\nDisallow: /assets/\n"
    assert codes(text).count("blocks-resources") == 1


def test_ordinary_directories_are_not_resource_warnings():
    assert "blocks-resources" not in codes("User-agent: *\nDisallow: /admin/\nDisallow: /search\n")


def test_sitemap_issues_are_included():
    text = "User-agent: *\nDisallow: /x\nSitemap: /sitemap.xml\nSitemap: ftp://e.com/s.xml\n"
    assert {"sitemap-not-absolute", "sitemap-bad-scheme"} <= set(codes(text))


def test_issues_sorted_by_severity_then_line():
    text = "Crawl-delay: 5\nDisallow: /x\nUser-agent: *\nDisallow: /\n"
    severities = [i.severity for i in lint(parse(text))]
    assert severities == sorted(severities, key=[ERROR, WARNING, INFO].index)


def test_helpers():
    issues = lint(parse("User-agent: *\nDisallow: /\nCrawl-delay: 1\n"))
    assert worst_severity(issues) == ERROR
    assert worst_severity([]) is None
    assert all(i.severity == ERROR for i in at_or_above(issues, ERROR))
    assert len(at_or_above(issues, INFO)) == len(issues)
    assert set(issues[0].to_dict()) == {"code", "severity", "line", "message", "hint"}


def test_rfc_profile_reports_typos_as_unknown():
    assert "unknown-directive" in codes("User-agent: *\nDissallow: /x\n", profile="rfc")
