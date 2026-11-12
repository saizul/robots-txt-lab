"""Data structures for a parsed robots.txt file."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Rule:
    """One ``allow`` or ``disallow`` line."""

    allow: bool
    #: The value as written, with surrounding whitespace removed.
    path: str
    #: The value after percent-encoding normalisation; this is what is matched.
    pattern: str
    line: int

    @property
    def directive(self) -> str:
        return "allow" if self.allow else "disallow"

    @property
    def priority(self) -> int:
        """Specificity: the number of octets in the normalised pattern."""
        return len(self.pattern)

    def __str__(self) -> str:
        return f"{self.directive}: {self.path}"


@dataclass
class Group:
    """A group: one or more ``user-agent`` lines followed by rules."""

    #: User-agent values as written.
    agents: list[str] = field(default_factory=list)
    #: Lower-cased product tokens for ``agents`` (``*`` for the global group).
    tokens: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    #: ``allow:`` / ``disallow:`` lines with no value; crawlers ignore them.
    empty_rules: list[int] = field(default_factory=list)
    start_line: int = 0
    #: Line numbers of the user-agent lines.
    agent_lines: list[int] = field(default_factory=list)

    @property
    def is_global(self) -> bool:
        return "*" in self.tokens


@dataclass(frozen=True)
class Directive:
    """Any other ``key: value`` line (sitemap, crawl-delay, unknown keys)."""

    #: Canonical lower-case key (typos already mapped, e.g. ``site-map`` -> ``sitemap``).
    key: str
    raw_key: str
    value: str
    line: int
    #: Index into ``RobotsTxt.groups`` of the group the line appeared in, if any.
    group: Optional[int] = None


@dataclass(frozen=True)
class ParseNote:
    """Something the parser noticed while reading; the linter turns these into issues."""

    kind: str
    line: int
    text: str
    detail: str = ""


@dataclass
class RobotsTxt:
    groups: list[Group] = field(default_factory=list)
    sitemaps: list[Directive] = field(default_factory=list)
    #: Directives other than user-agent / allow / disallow / sitemap.
    others: list[Directive] = field(default_factory=list)
    notes: list[ParseNote] = field(default_factory=list)
    #: Raw lines (after BOM removal and truncation), for the linter and reports.
    lines: list[str] = field(default_factory=list)
    size_bytes: int = 0
    had_bom: bool = False
    truncated: bool = False
    #: True when bytes could not be decoded as UTF-8 and were replaced.
    decode_errors: bool = False
    #: The key spellings seen, for case checks: (line, raw_key, canonical_key).
    keys: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def sitemap_urls(self) -> list[str]:
        return [d.value for d in self.sitemaps]

    def groups_for_token(self, token: str) -> list[Group]:
        token = token.lower()
        return [g for g in self.groups if token in g.tokens]
