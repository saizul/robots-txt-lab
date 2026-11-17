import io
import json

from robots_txt_lab.cli import EXIT_FAIL, EXIT_OK, EXIT_USAGE, Context, main
from robots_txt_lab.lint import CHECKS, Issue
from robots_txt_lab.output import render_lint_github, render_lint_sarif

PROBLEMS = (
    "User-agent: *\nDisallow: /\nCrawl-delay: 5 # robots-txt-lab: disable=crawl-delay-ignored\nSitemap: /sitemap.xml\n"
)


def run(argv, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, Context(out, err, io.StringIO(stdin)))
    return code, out.getvalue(), err.getvalue()


def write(tmp_path, text=PROBLEMS, name="robots.txt"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_sarif_structure(tmp_path):
    path = write(tmp_path)
    code, out, _ = run(["lint", path, "--format", "sarif"])
    assert code == EXIT_FAIL
    log = json.loads(out)
    assert log["version"] == "2.1.0" and "sarif" in log["$schema"]
    run_ = log["runs"][0]
    driver = run_["tool"]["driver"]
    assert driver["name"] == "robots-txt-lab"
    rule_ids = [r["id"] for r in driver["rules"]]
    assert rule_ids == sorted(set(rule_ids))
    by_id = {r["id"]: r for r in driver["rules"]}
    assert by_id["blocks-entire-site"]["defaultConfiguration"]["level"] == "error"
    assert by_id["blocks-entire-site"]["shortDescription"]["text"] == CHECKS["blocks-entire-site"][1]
    for result in run_["results"]:
        assert driver["rules"][result["ruleIndex"]]["id"] == result["ruleId"]
        assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == path.replace("\\", "/")
    whole = next(r for r in run_["results"] if r["ruleId"] == "blocks-entire-site")
    assert whole["level"] == "error"
    assert whole["locations"][0]["physicalLocation"]["region"] == {"startLine": 2}
    assert "Hint:" in whole["message"]["text"]


def test_sarif_marks_suppressed_results(tmp_path):
    _, out, _ = run(["lint", write(tmp_path), "--format", "sarif"])
    results = json.loads(out)["runs"][0]["results"]
    delay = [r for r in results if r["ruleId"] == "crawl-delay-ignored"]
    assert len(delay) == 1 and delay[0]["suppressions"] == [{"kind": "inSource"}]
    assert all("suppressions" not in r for r in results if r["ruleId"] != "crawl-delay-ignored")


def test_sarif_levels_and_lineless_issue():
    issues = [
        Issue("size-near-limit", "warning", None, "big"),
        Issue("bom", "info", 1, "bom"),
    ]
    log = json.loads(render_lint_sarif(issues, "./public/robots.txt"))
    results = log["runs"][0]["results"]
    assert [r["level"] for r in results] == ["warning", "note"]
    assert "region" not in results[0]["locations"][0]["physicalLocation"]
    assert results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "public/robots.txt"


def test_sarif_for_url_and_stdin_sources():
    issue = [Issue("bom", "info", 1, "bom")]
    url = json.loads(render_lint_sarif(issue, "https://example.com/robots.txt"))
    assert url["runs"][0]["artifacts"][0]["location"]["uri"] == "https://example.com/robots.txt"
    stdin = json.loads(render_lint_sarif(issue, "-"))
    assert stdin["runs"][0]["artifacts"][0]["location"]["uri"] == "robots.txt"


def test_sarif_with_no_issues(tmp_path):
    path = write(tmp_path, "User-agent: *\nDisallow: /private/\n")
    code, out, _ = run(["lint", path, "--format", "sarif"])
    assert code == EXIT_OK
    log = json.loads(out)
    assert log["runs"][0]["results"] == [] and log["runs"][0]["tool"]["driver"]["rules"] == []


def test_github_annotations(tmp_path):
    path = write(tmp_path)
    code, out, _ = run(["lint", path, "--format", "github"])
    assert code == EXIT_FAIL
    lines = out.splitlines()
    assert any(ln.startswith("::error file=") and ",line=2," in ln for ln in lines)
    assert all(ln.startswith(("::error ", "::warning ", "::notice ")) for ln in lines)
    assert not any("crawl-delay-ignored" in ln for ln in lines)


def test_github_escaping():
    issue = Issue("invalid-line", "warning", 3, "50% of\nlines", "a, b: c")
    out = render_lint_github([issue], "dir,x/robots:1.txt")
    assert out == (
        "::warning file=dir%2Cx/robots%3A1.txt,line=3,title=robots-txt-lab invalid-line"
        "::50%25 of%0Alines (hint: a, b: c)\n"
    )
    assert render_lint_github([Issue("no-groups", "info", None, "x")], "r.txt") == (
        "::notice file=r.txt,title=robots-txt-lab no-groups::x\n"
    )


def test_text_output_counts_suppressed(tmp_path):
    _, out, _ = run(["lint", write(tmp_path), "--fail-on", "never"])
    assert out.rstrip().endswith(", 1 suppressed")
    assert "crawl-delay-ignored" not in out
    clean = write(
        tmp_path, "User-agent: *\nDisallow: /x\nCrawl-delay: 5 # robots-txt-lab: disable=crawl-delay-ignored\n", "c.txt"
    )
    _, out, _ = run(["lint", clean])
    assert out.endswith("no issues found, 1 suppressed\n")


def test_json_output_lists_suppressed(tmp_path):
    _, out, _ = run(["lint", write(tmp_path), "--format", "json", "--fail-on", "never"])
    data = json.loads(out)
    assert [i["code"] for i in data["suppressed"]] == ["crawl-delay-ignored"]
    assert "crawl-delay-ignored" not in [i["code"] for i in data["issues"]]


def test_no_inline_ignores(tmp_path):
    _, out, _ = run(["lint", write(tmp_path), "--no-inline-ignores", "--fail-on", "never"])
    assert "[crawl-delay-ignored]" in out and "suppressed" not in out


def test_ignore_flag_applies_to_suppressed_too(tmp_path):
    _, out, _ = run(["lint", write(tmp_path), "--format", "json", "--ignore", "crawl-delay-ignored"])
    assert json.loads(out)["suppressed"] == []


def test_suppressed_error_does_not_fail_the_run(tmp_path):
    path = write(tmp_path, "User-agent: *\nDisallow: / # robots-txt-lab: disable=blocks-entire-site\n")
    code, _, _ = run(["lint", path])
    assert code == EXIT_OK


def test_list_checks():
    code, out, _ = run(["lint", "--list-checks"])
    assert code == EXIT_OK
    lines = out.splitlines()
    assert len(lines) == len(CHECKS)
    assert lines[0].split()[:2] == ["rule-outside-group", "error"]


def test_lint_without_source_is_a_usage_error():
    code, _, err = run(["lint"])
    assert code == EXIT_USAGE and "lint needs" in err


def test_sarif_is_only_offered_by_lint(tmp_path):
    code, _, _ = run(["test", write(tmp_path), "/x", "--format", "sarif"])
    assert code == EXIT_USAGE


def test_stdin_source(tmp_path):
    code, out, _ = run(["lint", "-", "--format", "github"], stdin="User-agent: *\nDisallow: /\n")
    assert code == EXIT_FAIL and "file=robots.txt," in out
