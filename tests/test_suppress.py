import re
from pathlib import Path

import pytest

from robots_txt_lab import CHECKS, lint, lint_report, parse, parse_suppressions

ROOT = Path(__file__).resolve().parent.parent


def codes(issues):
    return [i.code for i in issues]


def test_parse_same_line_next_line_and_file():
    lines = [
        "# robots-txt-lab: disable-file=bom,directive-case",
        "User-agent: *",
        "Disallow: /wp-includes/   # robots-txt-lab: disable=blocks-resources",
        "# robots-txt-lab: disable-next-line=crawl-delay-ignored",
        "",
        "# another comment",
        "Crawl-delay: 5",
    ]
    s = parse_suppressions(lines)
    assert not s.malformed
    assert [(x.kind, x.line, x.target, x.codes) for x in s.items] == [
        ("disable-file", 1, None, ("bom", "directive-case")),
        ("disable", 3, 3, ("blocks-resources",)),
        ("disable-next-line", 4, 7, ("crawl-delay-ignored",)),
    ]


def test_marker_is_case_insensitive_and_accepts_space_separator():
    s = parse_suppressions(["Crawl-delay: 5 # Robots-Txt-Lab: DISABLE crawl-delay-ignored, bom"])
    assert s.items[0].kind == "disable"
    assert s.items[0].codes == ("crawl-delay-ignored", "bom")


@pytest.mark.parametrize(
    "comment",
    [
        "# robots-txt-lab: disable=",
        "# robots-txt-lab: disable",
        "# robots-txt-lab: enable=bom",
        "# robots-txt-lab: disable=Bad Code!",
    ],
)
def test_malformed_comments(comment):
    s = parse_suppressions([comment, "User-agent: *"])
    assert not s.items
    assert s.malformed and s.malformed[0][0] == 1


def test_disable_next_line_at_end_of_file_is_malformed():
    s = parse_suppressions(["User-agent: *", "# robots-txt-lab: disable-next-line=bom"])
    assert not s.items and s.malformed == [(2, "robots-txt-lab: disable-next-line=bom")]


def test_ordinary_comments_are_ignored():
    s = parse_suppressions(["# robots.txt for example.com", "User-agent: * # all crawlers"])
    assert not s


def test_same_line_suppression():
    text = "User-agent: *\nDisallow: /private/\nCrawl-delay: 5 # robots-txt-lab: disable=crawl-delay-ignored\n"
    report = lint_report(parse(text))
    assert "crawl-delay-ignored" not in codes(report.issues)
    assert codes(report.suppressed) == ["crawl-delay-ignored"]
    # The public lint() drops suppressed issues too.
    assert "crawl-delay-ignored" not in codes(lint(parse(text)))


def test_suppression_only_covers_its_line():
    text = (
        "User-agent: *\n"
        "Crawl-delay: 5 # robots-txt-lab: disable=crawl-delay-ignored\n"
        "User-agent: bingbot\n"
        "Disallow: /x\n"
        "Crawl-delay: 9\n"
    )
    issues = lint(parse(text))
    assert [i.line for i in issues if i.code == "crawl-delay-ignored"] == [5]


def test_next_line_suppression_skips_blank_and_comment_lines():
    text = (
        "User-agent: *\n"
        "# robots-txt-lab: disable-next-line=noindex-unsupported\n"
        "\n"
        "# legacy rule kept for an old crawler\n"
        "Noindex: /old/\n"
        "Disallow: /tmp/\n"
    )
    report = lint_report(parse(text))
    assert codes(report.suppressed) == ["noindex-unsupported"]
    assert "unused-suppression" not in codes(report.issues)


def test_file_suppression_covers_issues_without_a_line():
    text = "﻿user-AGENT: *\nDisallow: /x\n# robots-txt-lab: disable-file=bom, directive-case\n"
    report = lint_report(parse(text))
    assert sorted(codes(report.suppressed)) == ["bom", "directive-case"]
    big = "User-agent: *\nDisallow: /x\n# robots-txt-lab: disable-file=size-near-limit\n" + "#" * 470_000 + "\n"
    report = lint_report(parse(big))
    assert codes(report.suppressed) == ["size-near-limit"]
    assert report.suppressed[0].line is None


def test_all_keyword():
    text = "User-agent: *\nDisallow: /\n# robots-txt-lab: disable-file=all\n"
    report = lint_report(parse(text))
    assert report.issues == []
    assert "blocks-entire-site" in codes(report.suppressed)


def test_unused_suppression_is_reported():
    text = "User-agent: *\nDisallow: /private/ # robots-txt-lab: disable=crawl-delay-ignored\n"
    issues = lint(parse(text))
    unused = [i for i in issues if i.code == "unused-suppression"]
    assert len(unused) == 1 and unused[0].line == 2 and unused[0].severity == "info"


def test_unknown_code_and_malformed_comment_are_warnings():
    text = (
        "User-agent: *\nDisallow: /x # robots-txt-lab: disable=no-such-check\n# robots-txt-lab: disable-forever=bom\n"
    )
    issues = lint(parse(text))
    bad = [(i.line, i.severity) for i in issues if i.code == "invalid-suppression"]
    assert bad == [(2, "warning"), (3, "warning")]
    # An unknown code is not also reported as unused.
    assert "unused-suppression" not in codes(issues)


def test_inline_suppressions_can_be_turned_off():
    text = "User-agent: *\nDisallow: /x\nCrawl-delay: 5 # robots-txt-lab: disable=crawl-delay-ignored\n"
    report = lint_report(parse(text), inline_suppressions=False)
    assert "crawl-delay-ignored" in codes(report.issues)
    assert report.suppressed == []
    assert "unused-suppression" not in codes(report.issues)


def test_suppression_comments_do_not_change_matching():
    from robots_txt_lab import Robots

    plain = Robots.from_text("User-agent: *\nDisallow: /a\n")
    commented = Robots.from_text("User-agent: *\nDisallow: /a # robots-txt-lab: disable=all\n")
    for path in ("/a", "/a/b", "/b"):
        assert plain.allowed(path, "Googlebot") == commented.allowed(path, "Googlebot")


def test_every_check_is_documented_in_the_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+)+|bom)`", readme))
    missing = [c for c in CHECKS if c not in documented]
    assert missing == []


def test_every_emitted_code_is_in_the_catalog():
    examples = [ROOT / "examples" / "problems.robots.txt", ROOT / "examples" / "robots.txt"]
    for path in examples:
        for issue in lint(parse(path.read_bytes())):
            assert issue.code in CHECKS, issue.code
            assert CHECKS[issue.code][0] in ("error", "warning", "info")
