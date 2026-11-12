"""Command-line interface: ``robots-txt-lab test | lint | diff | fetch | sitemaps``."""

from __future__ import annotations

import argparse
import sys
from typing import Callable, List, Optional, Sequence, TextIO, Tuple

from ._version import __version__
from .diff import DEFAULT_AGENTS, diff
from .fetch import Transport, fetch
from .lint import SEVERITIES, at_or_above, lint
from .output import (
    envelope,
    render_diff_text,
    render_fetch_text,
    render_lint_text,
    render_sitemaps_text,
    render_test_text,
    to_json,
)
from .parser import MAX_BYTES, PROFILES
from .robots import Robots

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


class CliError(Exception):
    pass


def _is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


class Context:
    """IO and the fetch transport, injectable for tests."""

    def __init__(
        self,
        stdout: Optional[TextIO] = None,
        stderr: Optional[TextIO] = None,
        stdin: Optional[TextIO] = None,
        transport: Optional[Transport] = None,
    ) -> None:
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr
        self.stdin = stdin or sys.stdin
        self.transport = transport


def load_robots(source: str, args: argparse.Namespace, ctx: Context) -> Tuple[Robots, Optional[str]]:
    """Load from a file, ``-`` (stdin) or a URL (fetched, with HTTP status handling).

    Returns the policy and the robots.txt URL when it was fetched.
    """
    if _is_url(source):
        result = fetch(
            source, profile=args.profile, timeout=args.timeout, transport=ctx.transport, max_bytes=args.max_bytes
        )
        if result.outcome != "ok":
            ctx.stderr.write(f"note: {result.requested_url}: {result.reason}; {result.robots.access}\n")
        return result.robots, result.requested_url
    if source == "-":
        data = getattr(ctx.stdin, "buffer", None)
        content = data.read() if data is not None else ctx.stdin.read().encode("utf-8")
    else:
        try:
            with open(source, "rb") as fh:
                content = fh.read()
        except OSError as exc:
            raise CliError(f"cannot read {source}: {exc.strerror or exc}") from exc
    return Robots.from_text(content, profile=args.profile, max_bytes=args.max_bytes), None


def _read_lines(path: str) -> List[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError as exc:
        raise CliError(f"cannot read {path}: {exc.strerror or exc}") from exc


def _agents(args: argparse.Namespace, default: Sequence[str]) -> List[str]:
    return list(args.user_agent) if args.user_agent else list(default)


# -- commands -----------------------------------------------------------------


def cmd_test(args: argparse.Namespace, ctx: Context) -> int:
    robots, _ = load_robots(args.robots, args, ctx)
    agents = _agents(args, ["Googlebot"])
    checks: List[Tuple[str, str, Optional[bool]]] = []
    for url in args.urls:
        for agent in agents:
            checks.append((url, agent, None if args.expect is None else args.expect == "allowed"))
    if args.urls_file:
        for url in _read_lines(args.urls_file):
            for agent in agents:
                checks.append((url, agent, None if args.expect is None else args.expect == "allowed"))
    if args.cases:
        for n, line in enumerate(_read_lines(args.cases), start=1):
            parts = line.split()
            if len(parts) < 2 or parts[0].lower() not in ("allow", "allowed", "disallow", "disallowed"):
                raise CliError(f"{args.cases}: case {n}: expected '<allow|disallow> <url> [user-agent]'")
            agent = " ".join(parts[2:]) or agents[0]
            checks.append((parts[1], agent, parts[0].lower().startswith("allow")))
    if not checks:
        raise CliError("test needs at least one URL, --urls-file or --cases")

    verdicts = []
    failures = []
    for url, agent, expected in checks:
        v = robots.check(url, agent)
        verdicts.append(v)
        if expected is not None and v.allowed != expected:
            want = "allowed" if expected else "disallowed"
            failures.append(f"{agent} {url}: expected {want}")
    if args.format == "json":
        ctx.stdout.write(
            to_json(
                envelope(
                    "test",
                    access=robots.access,
                    results=[v.to_dict() for v in verdicts],
                    failures=failures,
                )
            )
        )
    else:
        ctx.stdout.write(render_test_text(verdicts, failures))
    return EXIT_FAIL if failures else EXIT_OK


def cmd_lint(args: argparse.Namespace, ctx: Context) -> int:
    robots, url = load_robots(args.robots, args, ctx)
    if robots.access != "parsed":
        raise CliError(f"nothing to lint: {robots.access_reason}")
    issues = lint(robots.parsed, profile=args.profile, robots_url=url or args.robots_url)
    if args.ignore:
        ignored = {c.strip() for c in ",".join(args.ignore).split(",") if c.strip()}
        issues = [i for i in issues if i.code not in ignored]
    if args.format == "json":
        ctx.stdout.write(to_json(envelope("lint", source=args.robots, issues=[i.to_dict() for i in issues])))
    else:
        ctx.stdout.write(render_lint_text(issues, args.robots))
    if args.fail_on == "never":
        return EXIT_OK
    return EXIT_FAIL if at_or_above(issues, args.fail_on) else EXIT_OK


def cmd_diff(args: argparse.Namespace, ctx: Context) -> int:
    old, _ = load_robots(args.old, args, ctx)
    new, _ = load_robots(args.new, args, ctx)
    urls = list(args.url or [])
    if args.urls_file:
        urls.extend(_read_lines(args.urls_file))
    result = diff(old, new, urls or None, _agents(args, DEFAULT_AGENTS))
    if args.format == "json":
        ctx.stdout.write(to_json(envelope("diff", old=args.old, new=args.new, **result.to_dict())))
    else:
        ctx.stdout.write(render_diff_text(result))
    return EXIT_FAIL if args.fail_on_change and result.verdict_changes else EXIT_OK


def cmd_fetch(args: argparse.Namespace, ctx: Context) -> int:
    result = fetch(
        args.url,
        profile=args.profile,
        timeout=args.timeout,
        transport=ctx.transport,
        max_bytes=args.max_bytes,
        **({"user_agent": args.request_ua} if args.request_ua else {}),
    )
    if args.save and result.outcome == "ok":
        with open(args.save, "wb") as fh:
            fh.write(result.body)
    issues = []
    if args.lint and result.outcome == "ok":
        issues = lint(result.robots.parsed, profile=args.profile, robots_url=result.requested_url)
    if args.format == "json":
        payload = envelope("fetch", **result.to_dict())
        if args.lint:
            payload["issues"] = [i.to_dict() for i in issues]
        ctx.stdout.write(to_json(payload))
    else:
        ctx.stdout.write(render_fetch_text(result))
        if args.lint and result.outcome == "ok":
            ctx.stdout.write("\n" + render_lint_text(issues, result.requested_url))
    return EXIT_OK if result.outcome == "ok" else EXIT_FAIL


def cmd_sitemaps(args: argparse.Namespace, ctx: Context) -> int:
    robots, _ = load_robots(args.robots, args, ctx)
    if args.format == "json":
        ctx.stdout.write(to_json(envelope("sitemaps", sitemaps=robots.sitemaps)))
    else:
        ctx.stdout.write(render_sitemaps_text(robots))
    return EXIT_OK


# -- parser -----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--profile",
        choices=PROFILES,
        default="google",
        help="matching behaviour: google (default) or strict rfc (RFC 9309 only)",
    )
    common.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    common.add_argument("--timeout", type=float, default=10.0, help="fetch timeout in seconds (default 10)")
    common.add_argument("--max-bytes", type=int, default=MAX_BYTES, help=argparse.SUPPRESS)

    ua = argparse.ArgumentParser(add_help=False)
    ua.add_argument(
        "-a",
        "--user-agent",
        "--ua",
        action="append",
        metavar="UA",
        help="crawler token or full user agent string; repeat for several",
    )

    parser = argparse.ArgumentParser(
        prog="robots-txt-lab",
        description="Parse, test, lint and diff robots.txt files the way RFC 9309 and Google read them.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    t = sub.add_parser("test", parents=[common, ua], help="check whether URLs are allowed")
    t.add_argument("robots", help="robots.txt file, '-' for stdin, or a site URL to fetch")
    t.add_argument("urls", nargs="*", help="URLs or paths to test")
    t.add_argument("--urls-file", help="file with one URL per line")
    t.add_argument("--cases", help="file of '<allow|disallow> <url> [user-agent]' expectations")
    t.add_argument("--expect", choices=("allowed", "disallowed"), help="exit 1 unless every URL has this verdict")
    t.set_defaults(func=cmd_test)

    li = sub.add_parser("lint", parents=[common], help="find problems in a robots.txt")
    li.add_argument("robots", help="robots.txt file, '-' for stdin, or a site URL to fetch")
    li.add_argument(
        "--fail-on",
        choices=(*SEVERITIES, "never"),
        default="error",
        help="exit 1 when an issue of this severity or worse is found (default: error)",
    )
    li.add_argument("--ignore", action="append", metavar="CODES", help="comma-separated issue codes to skip")
    li.add_argument("--robots-url", help="where the file is served, for sitemap host checks")
    li.set_defaults(func=cmd_lint)

    d = sub.add_parser("diff", parents=[common, ua], help="compare two robots.txt versions")
    d.add_argument("old", help="old robots.txt (file, '-' or URL)")
    d.add_argument("new", help="new robots.txt (file, '-' or URL)")
    d.add_argument("-u", "--url", action="append", help="URL or path to test; repeat for several")
    d.add_argument("--urls-file", help="file with one URL per line")
    d.add_argument("--fail-on-change", action="store_true", help="exit 1 when any verdict changes")
    d.set_defaults(func=cmd_diff)

    f = sub.add_parser("fetch", parents=[common], help="fetch a robots.txt and show how crawlers treat it")
    f.add_argument("url", help="site URL or robots.txt URL")
    f.add_argument("--save", help="write the fetched body to this file")
    f.add_argument("--lint", action="store_true", help="also lint the fetched file")
    f.add_argument("--request-ua", help="User-Agent header for the request")
    f.set_defaults(func=cmd_fetch)

    s = sub.add_parser("sitemaps", parents=[common], help="list the sitemap URLs")
    s.add_argument("robots", help="robots.txt file, '-' for stdin, or a site URL to fetch")
    s.set_defaults(func=cmd_sitemaps)
    return parser


def main(argv: Optional[Sequence[str]] = None, ctx: Optional[Context] = None) -> int:
    ctx = ctx or Context()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits on --help, --version and errors
        return int(exc.code or 0)
    if not getattr(args, "func", None):
        parser.print_help(ctx.stdout)
        return EXIT_USAGE
    run: Callable[[argparse.Namespace, Context], int] = args.func
    try:
        return run(args, ctx)
    except CliError as exc:
        ctx.stderr.write(f"robots-txt-lab: {exc}\n")
        return EXIT_USAGE
    except BrokenPipeError:
        return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
