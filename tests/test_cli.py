import io
import json
import subprocess
import sys

import pytest

from robots_txt_lab.cli import EXIT_FAIL, EXIT_OK, EXIT_USAGE, Context, main

from .conftest import FakeTransport

ROBOTS = "User-agent: *\nDisallow: /private/\nCrawl-delay: 5\nSitemap: https://example.com/sitemap.xml\n"


class Run:
    def __init__(self, argv, transport=None, stdin=""):
        self.out, self.err = io.StringIO(), io.StringIO()
        ctx = Context(self.out, self.err, io.StringIO(stdin), transport)
        self.code = main(argv, ctx)

    @property
    def json(self):
        return json.loads(self.out.getvalue())


@pytest.fixture
def robots_file(tmp_path):
    p = tmp_path / "robots.txt"
    p.write_text(ROBOTS, encoding="utf-8")
    return str(p)


def test_no_command_prints_help():
    r = Run([])
    assert r.code == EXIT_USAGE
    assert "test" in r.out.getvalue()


def test_version(capsys):
    assert main(["--version"]) == 0
    assert "0.1.0" in capsys.readouterr().out


def test_test_text(robots_file):
    r = Run(["test", robots_file, "https://example.com/private/a", "/public"])
    assert r.code == EXIT_OK
    out = r.out.getvalue()
    assert "DISALLOWED Googlebot" in out and "disallow: /private/ (line 2)" in out
    assert "ALLOWED    Googlebot" in out
    assert "2 check(s): 1 allowed, 1 disallowed" in out


def test_test_json_with_several_agents(robots_file):
    r = Run(["test", robots_file, "/private/a", "--ua", "Googlebot", "-a", "Bingbot", "--format", "json"])
    data = r.json
    assert data["command"] == "test" and data["tool"] == "robots-txt-lab"
    assert [x["user_agent"] for x in data["results"]] == ["Googlebot", "Bingbot"]
    assert all(x["allowed"] is False for x in data["results"])


def test_expect(robots_file):
    assert Run(["test", robots_file, "/public", "--expect", "allowed"]).code == EXIT_OK
    r = Run(["test", robots_file, "/private/x", "--expect", "allowed"])
    assert r.code == EXIT_FAIL
    assert "FAIL Googlebot /private/x: expected allowed" in r.out.getvalue()


def test_cases_file(robots_file, tmp_path):
    cases = tmp_path / "cases.txt"
    cases.write_text("# expectations\nallow /\ndisallow /private/x\ndisallow /private/y Bingbot\nallow /private/z\n")
    r = Run(["test", robots_file, "--cases", str(cases), "--format", "json"])
    assert r.code == EXIT_FAIL
    assert r.json["failures"] == ["Googlebot /private/z: expected allowed"]
    bad = tmp_path / "bad.txt"
    bad.write_text("maybe /x\n")
    assert Run(["test", robots_file, "--cases", str(bad)]).code == EXIT_USAGE


def test_urls_file(robots_file, tmp_path):
    urls = tmp_path / "urls.txt"
    urls.write_text("/a\n\n/private/b\n")
    r = Run(["test", robots_file, "--urls-file", str(urls), "--format", "json"])
    assert [x["allowed"] for x in r.json["results"]] == [True, False]


def test_test_needs_urls(robots_file):
    r = Run(["test", robots_file])
    assert r.code == EXIT_USAGE
    assert "needs at least one URL" in r.err.getvalue()


def test_missing_file():
    r = Run(["test", "/nonexistent/robots.txt", "/"])
    assert r.code == EXIT_USAGE
    assert "cannot read" in r.err.getvalue()


def test_stdin():
    r = Run(["test", "-", "/private/x"], stdin=ROBOTS)
    assert "DISALLOWED" in r.out.getvalue()


def test_test_against_a_url_uses_fetch_status():
    t = FakeTransport({"https://example.com/robots.txt": (503, {}, b"")})
    r = Run(["test", "https://example.com/", "/anything"], transport=t)
    assert "DISALLOWED" in r.out.getvalue()
    assert "unreachable" in r.out.getvalue()
    assert "HTTP 503" in r.err.getvalue()


def test_profile_flag(tmp_path):
    p = tmp_path / "r.txt"
    p.write_text("User-agent: *\nDissallow: /x\n")
    assert "DISALLOWED" in Run(["test", str(p), "/x"]).out.getvalue()
    assert "DISALLOWED" not in Run(["test", str(p), "/x", "--profile", "rfc"]).out.getvalue()


def test_lint_exit_codes(robots_file, tmp_path):
    r = Run(["lint", robots_file])
    assert r.code == EXIT_OK  # only a warning
    assert "crawl-delay is ignored by Google" in r.out.getvalue()
    assert Run(["lint", robots_file, "--fail-on", "warning"]).code == EXIT_FAIL
    assert Run(["lint", robots_file, "--fail-on", "warning", "--ignore", "crawl-delay-ignored"]).code == EXIT_OK
    bad = tmp_path / "bad.txt"
    bad.write_text("User-agent: *\nDisallow: /\n")
    assert Run(["lint", str(bad)]).code == EXIT_FAIL
    assert Run(["lint", str(bad), "--fail-on", "never"]).code == EXIT_OK


def test_lint_json(robots_file):
    data = Run(["lint", robots_file, "--format", "json"]).json
    assert data["issues"][0]["code"] == "crawl-delay-ignored"
    assert data["issues"][0]["line"] == 3


def test_lint_clean_text(tmp_path):
    p = tmp_path / "ok.txt"
    p.write_text("User-agent: *\nDisallow: /x\n")
    assert "no issues found" in Run(["lint", str(p)]).out.getvalue()


def test_lint_of_unavailable_robots_is_a_usage_error():
    t = FakeTransport({})
    r = Run(["lint", "https://example.com/"], transport=t)
    assert r.code == EXIT_USAGE
    assert "nothing to lint" in r.err.getvalue()


def test_diff(tmp_path):
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    old.write_text("User-agent: *\nDisallow: /tmp/\n")
    new.write_text("User-agent: *\nDisallow: /search\n")
    r = Run(["diff", str(old), str(new), "-u", "/tmp/a", "-u", "/search?q=1", "--ua", "Googlebot"])
    out = r.out.getvalue()
    assert r.code == EXIT_OK
    assert "- [*] disallow: /tmp/" in out and "+ [*] disallow: /search" in out
    assert "/tmp/a  disallowed -> ALLOWED" in out
    assert "/search?q=1  allowed -> DISALLOWED" in out
    assert Run(["diff", str(old), str(new), "--fail-on-change"]).code == EXIT_FAIL
    assert Run(["diff", str(old), str(old), "--fail-on-change"]).code == EXIT_OK


def test_diff_json_and_urls_file(tmp_path):
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    urls = tmp_path / "urls.txt"
    old.write_text("User-agent: *\nDisallow: /a\n")
    new.write_text("User-agent: *\nDisallow: /b\n")
    urls.write_text("/a\n/b\n/c\n")
    data = Run(["diff", str(old), str(new), "--urls-file", str(urls), "--format", "json", "--ua", "x"]).json
    assert data["urls_tested"] == 3
    assert {c["url"] for c in data["verdict_changes"]} == {"/a", "/b"}


def test_fetch_command(tmp_path):
    body = ROBOTS.encode()
    t = FakeTransport(
        {
            "https://example.com/robots.txt": (301, {"Location": "https://www.example.com/robots.txt"}, b""),
            "https://www.example.com/robots.txt": (200, {"Content-Type": "text/plain"}, body),
        }
    )
    save = tmp_path / "saved.txt"
    r = Run(["fetch", "https://example.com/page", "--save", str(save), "--lint"], transport=t)
    out = r.out.getvalue()
    assert r.code == EXIT_OK
    assert "301  https://example.com/robots.txt" in out
    assert "Outcome: ok (HTTP 200)" in out
    assert "Sitemaps: 1" in out
    assert "crawl-delay" in out
    assert save.read_bytes() == body


def test_fetch_json_and_failure_exit():
    t = FakeTransport({"https://example.com/robots.txt": (404, {}, b"")})
    r = Run(["fetch", "https://example.com/", "--format", "json"], transport=t)
    assert r.code == EXIT_FAIL
    assert r.json["outcome"] == "unavailable" and r.json["access"] == "allow-all"


def test_fetch_request_ua():
    t = FakeTransport({"https://example.com/robots.txt": (200, {}, b"")})
    Run(["fetch", "https://example.com/", "--request-ua", "AuditBot/1.0"], transport=t)
    assert t.requests[0][1]["User-Agent"] == "AuditBot/1.0"


def test_sitemaps_command(robots_file):
    assert Run(["sitemaps", robots_file]).out.getvalue() == "https://example.com/sitemap.xml\n"
    assert Run(["sitemaps", robots_file, "--format", "json"]).json["sitemaps"] == ["https://example.com/sitemap.xml"]


def test_bad_arguments_return_usage(robots_file, capsys):
    assert main(["test", robots_file, "/", "--format", "xml"]) == 2
    capsys.readouterr()


def test_module_entry_point(robots_file):
    proc = subprocess.run(
        [sys.executable, "-m", "robots_txt_lab", "test", robots_file, "/private/x"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "DISALLOWED" in proc.stdout
