"""Text and JSON renderers for the CLI."""

from __future__ import annotations

import json
from typing import Any, List, Optional

from ._version import __version__
from .diff import DiffResult
from .fetch import FetchResult
from .lint import Issue
from .robots import Robots, Verdict


def to_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def envelope(command: str, **data: Any) -> dict:
    return {"tool": "robots-txt-lab", "version": __version__, "command": command, **data}


# -- test -------------------------------------------------------------------


def verdict_line(v: Verdict) -> str:
    state = "ALLOWED   " if v.allowed else "DISALLOWED"
    if v.rule is not None:
        why = f"{v.rule} (line {v.rule.line})"
    else:
        why = {
            "no-matching-rule": "no rule matches",
            "no-matching-group": "no group for this user agent and no '*' group",
            "robots-txt-always-allowed": "/robots.txt is always allowed",
            "unavailable-allow-all": "robots.txt unavailable (4xx): no restrictions",
            "unreachable-disallow-all": "robots.txt unreachable (5xx or network error): full disallow",
        }.get(v.reason, v.reason)
    group = f" [group {v.group_token}]" if v.group_token else ""
    return f"{state} {v.user_agent:<16} {v.url}  <- {why}{group}"


def render_test_text(verdicts: List[Verdict], failures: Optional[List[str]] = None) -> str:
    lines = [verdict_line(v) for v in verdicts]
    allowed = sum(v.allowed for v in verdicts)
    lines.append("")
    lines.append(f"{len(verdicts)} check(s): {allowed} allowed, {len(verdicts) - allowed} disallowed")
    for f in failures or []:
        lines.append(f"FAIL {f}")
    return "\n".join(lines) + "\n"


# -- lint -------------------------------------------------------------------


def render_lint_text(issues: List[Issue], source: str) -> str:
    if not issues:
        return f"{source}: no issues found\n"
    lines = []
    for i in issues:
        where = f"{source}:{i.line}" if i.line is not None else source
        lines.append(f"{where}: {i.severity}: {i.message} [{i.code}]")
        if i.hint:
            lines.append(f"    hint: {i.hint}")
    counts = {s: sum(1 for i in issues if i.severity == s) for s in ("error", "warning", "info")}
    lines.append("")
    lines.append(f"{counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info")
    return "\n".join(lines) + "\n"


# -- diff -------------------------------------------------------------------


def render_diff_text(result: DiffResult) -> str:
    lines: List[str] = []
    if result.rule_changes:
        lines.append("Rule changes:")
        for c in result.rule_changes:
            sign = "+" if c.change == "added" else "-"
            lines.append(f"  {sign} [{c.agents}] {c.directive}: {c.path}  (line {c.line})")
    for u in result.sitemaps_added:
        lines.append(f"  + sitemap: {u}")
    for u in result.sitemaps_removed:
        lines.append(f"  - sitemap: {u}")
    if lines:
        lines.append("")
    source = "derived from the rules" if result.derived_urls else "given"
    lines.append(f"Verdict changes ({len(result.urls_tested)} URL(s) {source} x {len(result.agents_tested)} agent(s)):")
    if not result.verdict_changes:
        lines.append("  none")
    for c in result.verdict_changes:
        arrow = "allowed -> DISALLOWED" if not c.after.allowed else "disallowed -> ALLOWED"
        rule = f"{c.after.rule} (line {c.after.rule.line})" if c.after.rule else c.after.reason
        lines.append(f"  {c.user_agent:<12} {c.url}  {arrow}  <- {rule}")
    return "\n".join(lines) + "\n"


# -- fetch ------------------------------------------------------------------


def render_fetch_text(result: FetchResult) -> str:
    lines = [f"robots.txt: {result.requested_url}"]
    for url, status in result.chain:
        lines.append(f"  {status if status is not None else 'ERR'}  {url}")
    meaning = {
        "ok": "parsed; its rules apply",
        "unavailable": "treated as unavailable: no crawl restrictions",
        "unreachable": "treated as unreachable: complete disallow",
    }[result.outcome]
    lines.append(f"Outcome: {result.outcome} ({result.reason}), {meaning}")
    if result.outcome == "ok":
        p = result.robots.parsed
        lines.append(f"Size: {len(result.body):,} bytes{' (truncated at 500 KiB)' if p.truncated else ''}")
        ctype = result.headers.get("content-type")
        if ctype:
            lines.append(f"Content-Type: {ctype}")
        lines.append(f"Groups: {len(p.groups)}")
        for g in p.groups:
            allow = sum(r.allow for r in g.rules)
            lines.append(
                f"  line {g.start_line}: {', '.join(g.agents)} - {allow} allow, {len(g.rules) - allow} disallow"
            )
        lines.append(f"Sitemaps: {len(p.sitemaps)}")
        for s in p.sitemap_urls:
            lines.append(f"  {s}")
    return "\n".join(lines) + "\n"


def render_sitemaps_text(robots: Robots) -> str:
    return "".join(f"{u}\n" for u in robots.sitemaps)
