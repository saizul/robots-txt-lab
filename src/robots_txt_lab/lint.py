"""Linter: problems that make a robots.txt behave differently than intended."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .agents import is_valid_token, product_token
from .matcher import literal_prefix
from .models import Group, RobotsTxt, Rule
from .parser import MAX_BYTES
from .robots import Robots
from .sitemaps import sitemap_problems

ERROR = "error"
WARNING = "warning"
INFO = "info"
SEVERITIES = (ERROR, WARNING, INFO)
_RANK = {ERROR: 0, WARNING: 1, INFO: 2}


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    line: Optional[int]
    message: str
    hint: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "line": self.line,
            "message": self.message,
            "hint": self.hint,
        }


#: Directives outside RFC 9309 that some crawlers read, and what Google does with them.
KNOWN_NONSTANDARD: Dict[str, tuple] = {
    "crawl-delay": (
        "crawl-delay-ignored",
        WARNING,
        "crawl-delay is ignored by Google (Bing and Yandex read it)",
        "Googlebot adjusts its crawl rate automatically; to slow it down temporarily, return 503 or 429.",
    ),
    "noindex": (
        "noindex-unsupported",
        WARNING,
        "noindex in robots.txt is not supported by Google (support ended in September 2019)",
        "Use a robots meta tag or an X-Robots-Tag header, and do not disallow the page.",
    ),
    "nofollow": ("nonstandard-directive", WARNING, "nofollow is not a robots.txt directive", ""),
    "host": ("host-directive", INFO, "host is a Yandex extension and is ignored by Google", ""),
    "clean-param": ("clean-param-directive", INFO, "clean-param is a Yandex extension and is ignored by Google", ""),
    "request-rate": ("nonstandard-directive", INFO, "request-rate is non-standard and ignored by Google", ""),
    "visit-time": ("nonstandard-directive", INFO, "visit-time is non-standard and ignored by Google", ""),
    "content-signal": ("nonstandard-directive", INFO, "content-signal is non-standard and ignored by Google", ""),
}

#: Typical stylesheet / script locations; disallowing them breaks rendering.
_RESOURCE_HINT = re.compile(
    r"\.css|\.js|\.mjs|/js\b|/css\b|/assets?\b|/static\b|/scripts?\b|/styles?\b|/themes?\b|"
    r"/wp-includes\b|/wp-content/(themes|plugins)\b|/_next/static\b|/build\b|/dist\b",
    re.IGNORECASE,
)

_SEARCH_AGENTS = ("googlebot", "*")
_TOKEN_PREFIX = re.compile(r"[A-Za-z_-]*")
_CANONICAL_CASES = {"user-agent": ("user-agent", "User-agent", "User-Agent")}


def _sample_resources(rule: Rule) -> List[str]:
    prefix = literal_prefix(rule.pattern) or "/"
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    base = prefix if prefix.endswith("/") else prefix.rsplit("/", 1)[0] + "/"
    lower = rule.pattern.lower()
    samples = []
    if ".css" in lower or "css" in lower or "style" in lower:
        samples.append(f"{base}site.css")
    if ".js" in lower or "js" in lower or "script" in lower:
        samples.append(f"{base}app.js")
    if not samples:
        samples = [f"{base}site.css", f"{base}app.js"]
    # Patterns like /*.css$ match the sample only if it keeps the suffix; the prefix is enough.
    return samples


def _blocks_whole_site(group: Group) -> Optional[Rule]:
    for r in group.rules:
        if not r.allow and r.pattern in ("/", "/*", "*"):
            return r
    return None


def lint(robots_txt: RobotsTxt, *, profile: str = "google", robots_url: Optional[str] = None) -> List[Issue]:
    """Run every check and return the issues, most severe first, then by line."""
    issues: List[Issue] = []
    add = issues.append
    robots = Robots(robots_txt, profile)

    # -- file level -------------------------------------------------------
    if robots_txt.had_bom:
        add(
            Issue(
                "bom",
                INFO,
                1,
                "the file starts with a UTF-8 byte order mark",
                "Google ignores it, but some other parsers read the first line as '\\ufeffUser-agent'.",
            )
        )
    if robots_txt.truncated:
        add(
            Issue(
                "size-limit",
                ERROR,
                None,
                f"the file is {robots_txt.size_bytes:,} bytes; content after {MAX_BYTES:,} bytes (500 KiB) is ignored",
                "Consolidate rules, for example by moving excluded content into fewer directories.",
            )
        )
    elif robots_txt.size_bytes > MAX_BYTES * 0.9:
        add(
            Issue(
                "size-near-limit",
                WARNING,
                None,
                f"the file is {robots_txt.size_bytes:,} bytes, close to the 500 KiB limit",
            )
        )
    if robots_txt.decode_errors:
        add(
            Issue(
                "not-utf8",
                WARNING,
                None,
                "the file is not valid UTF-8; invalid bytes were replaced",
                "Save the file as UTF-8. Characters outside UTF-8 may make rules invalid.",
            )
        )
    head = "\n".join(robots_txt.lines[:20]).lower()
    if "<html" in head or "<!doctype" in head or "<head" in head:
        add(
            Issue(
                "html-content",
                ERROR,
                1,
                "the file looks like an HTML page, not robots.txt",
                "The server probably returns an error or app page with status 200 for /robots.txt.",
            )
        )
    if not robots_txt.groups:
        add(Issue("no-groups", INFO, None, "no user-agent groups: every crawler may access everything"))

    # -- parser notes -------------------------------------------------------
    for note in robots_txt.notes:
        if note.kind == "typo":
            add(
                Issue(
                    "misspelled-directive",
                    WARNING,
                    note.line,
                    f"misspelled directive ({note.detail})",
                    "Google accepts this spelling, other crawlers may not.",
                )
            )
        elif note.kind == "missing-colon":
            add(
                Issue(
                    "missing-colon",
                    WARNING,
                    note.line,
                    f"missing ':' in {note.text.strip()!r}",
                    "Google accepts it, other crawlers may skip the line.",
                )
            )
        elif note.kind == "invalid-line":
            add(
                Issue(
                    "invalid-line",
                    WARNING,
                    note.line,
                    f"line ignored, not a 'field: value' pair: {note.text.strip()!r}",
                )
            )
        elif note.kind == "rule-outside-group":
            add(
                Issue(
                    "rule-outside-group",
                    ERROR,
                    note.line,
                    f"rule before any user-agent line is ignored: {note.text.strip()!r}",
                    "Add a 'User-agent: *' line above it.",
                )
            )
        elif note.kind == "invalid-user-agent":
            add(
                Issue(
                    "invalid-user-agent",
                    WARNING,
                    note.line,
                    f"user-agent value has no valid product token: {note.text.strip()!r}",
                )
            )

    # -- key spelling and case ----------------------------------------------------
    for line, raw_key, key in robots_txt.keys:
        if key in ("user-agent", "allow", "disallow", "sitemap") and raw_key.lower() == key:
            accepted = {key, key.capitalize(), *(_CANONICAL_CASES.get(key, ()))}
            if raw_key not in accepted:
                add(
                    Issue(
                        "directive-case",
                        INFO,
                        line,
                        f"unusual capitalisation {raw_key!r}",
                        f"Field names are case-insensitive, but '{key.capitalize()}' is the common form.",
                    )
                )

    # -- other directives ---------------------------------------------------
    for d in robots_txt.others:
        if d.key in KNOWN_NONSTANDARD:
            code, severity, message, hint = KNOWN_NONSTANDARD[d.key]
            add(Issue(code, severity, d.line, message, hint))
        else:
            add(
                Issue(
                    "unknown-directive",
                    WARNING,
                    d.line,
                    f"unknown directive {d.raw_key!r} is ignored",
                    "Google supports user-agent, allow, disallow and sitemap.",
                )
            )

    # -- groups ----------------------------------------------------------------
    for group in robots_txt.groups:
        names = ", ".join(group.agents) or "?"
        for value, line in zip(group.agents, group.agent_lines):
            if value and value != "*" and not is_valid_token(value) and product_token(value) not in ("", "*"):
                token = _TOKEN_PREFIX.match(value.strip()).group(0)
                add(
                    Issue(
                        "user-agent-token",
                        INFO,
                        line,
                        f"user-agent {value!r} is matched as the product token {token!r}",
                        "Only letters, '-' and '_' are part of the token; the rest is ignored.",
                    )
                )
        if not group.rules and not group.empty_rules:
            add(
                Issue(
                    "empty-group",
                    INFO,
                    group.start_line,
                    f"group for {names} has no rules, so it allows everything",
                    "If these agents should follow the '*' rules, remove the group.",
                )
            )
        for line in group.empty_rules:
            add(Issue("empty-rule", INFO, line, "rule without a path is ignored (an empty disallow allows everything)"))

        seen: Dict[tuple, int] = {}
        by_pattern: Dict[str, Rule] = {}
        for rule in group.rules:
            key = (rule.allow, rule.pattern)
            if key in seen:
                add(Issue("duplicate-rule", INFO, rule.line, f"duplicate of line {seen[key]}: {rule}"))
            else:
                seen[key] = rule.line
            other = by_pattern.get(rule.pattern)
            if other is not None and other.allow != rule.allow:
                add(
                    Issue(
                        "conflicting-rules",
                        WARNING,
                        rule.line,
                        f"allow and disallow for the same path {rule.path!r} (line {other.line}); allow wins",
                        "Remove one of the two rules to make the intent explicit.",
                    )
                )
            by_pattern.setdefault(rule.pattern, rule)

            p = rule.path
            if not p.startswith("/") and not p.startswith("*"):
                add(
                    Issue(
                        "path-no-leading-slash",
                        WARNING,
                        rule.line,
                        f"{rule} does not start with '/', so it never matches",
                        f"Write '/{p}'.",
                    )
                )
            if "$" in p[:-1]:
                add(
                    Issue(
                        "dollar-not-at-end",
                        WARNING,
                        rule.line,
                        f"'$' only anchors at the end of a pattern; here it is matched literally: {rule}",
                    )
                )
            if len(p) > 1 and p.endswith("*") and not p.endswith("$*"):
                add(
                    Issue(
                        "redundant-wildcard",
                        INFO,
                        rule.line,
                        f"trailing '*' is implied: {rule}",
                        f"'{p.rstrip('*')}' is equivalent.",
                    )
                )
            if not rule.allow and rule.pattern == "/robots.txt":
                add(
                    Issue(
                        "robots-txt-disallowed",
                        INFO,
                        rule.line,
                        "/robots.txt is always allowed; this rule has no effect",
                    )
                )
            if not rule.allow and re.search(r"[A-Z]", literal_prefix(p)):
                add(
                    Issue(
                        "path-case", INFO, rule.line, f"paths are case-sensitive: {rule} does not block {p.lower()!r}"
                    )
                )
            if p.startswith(("http://", "https://")):
                add(
                    Issue(
                        "absolute-url-rule",
                        ERROR,
                        rule.line,
                        f"rules take a path, not a full URL: {rule}",
                        "Use only the path, starting with '/'.",
                    )
                )

        whole = _blocks_whole_site(group)
        if whole is not None:
            allows = [r for r in group.rules if r.allow and r.pattern not in ("/", "/*")]
            important = any(t in _SEARCH_AGENTS for t in group.tokens)
            if not allows:
                add(
                    Issue(
                        "blocks-entire-site",
                        ERROR if important else WARNING,
                        whole.line,
                        f"{whole} blocks the entire site for {names}",
                        "Intended for a staging site? Remove it before launch.",
                    )
                )
            else:
                add(
                    Issue(
                        "blocks-entire-site",
                        INFO,
                        whole.line,
                        f"{whole} blocks everything for {names} except {len(allows)} allowed path(s)",
                    )
                )

    # -- CSS and JavaScript ----------------------------------------------------
    reported = set()
    # Googlebot, and every search crawler that falls back to the "*" group.
    for agent, label in (("Googlebot", "Googlebot"), ("*", "crawlers that use the '*' group")):
        for rule in robots.rules_for(agent):
            if rule.allow or rule.line in reported or rule.pattern in ("/", "/*", "*"):
                continue
            if not _RESOURCE_HINT.search(rule.path):
                continue
            blocked = [s for s in _sample_resources(rule) if not robots.check(s, agent).allowed]
            if blocked:
                reported.add(rule.line)
                add(
                    Issue(
                        "blocks-resources",
                        WARNING,
                        rule.line,
                        f"{rule} blocks CSS or JavaScript for {label} (e.g. {blocked[0]})",
                        "Search engines need CSS and JS to render pages; allow them, "
                        "e.g. 'Allow: /*.css$' and 'Allow: /*.js$'.",
                    )
                )

    # -- sitemaps ----------------------------------------------------------
    severity = {
        "sitemap-empty": ERROR,
        "sitemap-invalid-url": ERROR,
        "sitemap-not-absolute": ERROR,
        "sitemap-bad-scheme": ERROR,
        "sitemap-hash": WARNING,
        "sitemap-duplicate": INFO,
        "sitemap-cross-host": INFO,
        "sitemap-scheme-mismatch": WARNING,
    }
    for p in sitemap_problems(robots_txt, robots_url):
        add(Issue(p.kind, severity.get(p.kind, WARNING), p.line, f"{p.message}: {p.url!r}" if p.url else p.message))

    issues.sort(key=lambda i: (_RANK[i.severity], i.line if i.line is not None else 0, i.code))
    return issues


def worst_severity(issues: List[Issue]) -> Optional[str]:
    if not issues:
        return None
    return min((i.severity for i in issues), key=lambda s: _RANK[s])


def at_or_above(issues: List[Issue], threshold: str) -> List[Issue]:
    """Issues whose severity is ``threshold`` or worse."""
    limit = _RANK[threshold]
    return [i for i in issues if _RANK[i.severity] <= limit]
