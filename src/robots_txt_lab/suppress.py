"""Inline suppression comments for the linter.

Comments are invisible to crawlers, so a robots.txt can document why a lint
issue is accepted right where it happens::

    Disallow: /wp-includes/   # robots-txt-lab: disable=blocks-resources
    # robots-txt-lab: disable-next-line=crawl-delay-ignored
    Crawl-delay: 5
    # robots-txt-lab: disable-file=bom,directive-case

``disable`` applies to the line the comment is on, ``disable-next-line`` to the
next line that is not blank or a comment, and ``disable-file`` to the whole file
(including issues that have no line, such as ``size-near-limit``). Codes are
comma-separated; ``all`` matches every code. The marker is case-insensitive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

MARKER = "robots-txt-lab:"
ALL = "all"

_DIRECTIVE = re.compile(
    r"robots-txt-lab:\s*(?P<kind>disable-next-line|disable-file|disable)\s*(?:=\s*|\s+)(?P<codes>[A-Za-z0-9_,\s-]*)",
    re.IGNORECASE,
)
_CODE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class Suppression:
    """One ``robots-txt-lab: disable...`` comment."""

    kind: str
    #: The line the comment is on.
    line: int
    #: The line it applies to (``None`` for ``disable-file``).
    target: Optional[int]
    codes: Tuple[str, ...]

    def covers(self, code: str) -> bool:
        return ALL in self.codes or code in self.codes


@dataclass
class Suppressions:
    """All suppression comments of a file, plus comments that could not be read."""

    items: List[Suppression] = field(default_factory=list)
    #: ``(line, text)`` of markers with no or invalid codes.
    malformed: List[Tuple[int, str]] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.items or self.malformed)

    def match(self, code: str, line: Optional[int]) -> Optional[Suppression]:
        """The first suppression that silences ``code`` on ``line``, if any."""
        for s in self.items:
            if not s.covers(code):
                continue
            if s.kind == "disable-file" or (line is not None and s.target == line):
                return s
        return None


def _comment(raw: str) -> Optional[str]:
    _, sep, comment = raw.partition("#")
    return comment if sep else None


def _is_content(raw: str) -> bool:
    return bool(raw.split("#", 1)[0].strip(" \t"))


def parse_suppressions(lines: List[str]) -> Suppressions:
    """Find suppression comments in the raw lines of a robots.txt (1-based line numbers)."""
    result = Suppressions()
    for number, raw in enumerate(lines, start=1):
        comment = _comment(raw)
        if comment is None or MARKER not in comment.lower():
            continue
        m = _DIRECTIVE.search(comment)
        if m is None:
            result.malformed.append((number, comment.strip()))
            continue
        codes = tuple(c.strip().lower() for c in m.group("codes").split(",") if c.strip())
        if not codes or not all(_CODE.match(c) for c in codes):
            result.malformed.append((number, comment.strip()))
            continue
        kind = m.group("kind").lower()
        if kind == "disable":
            target: Optional[int] = number
        elif kind == "disable-next-line":
            target = next((n for n in range(number + 1, len(lines) + 1) if _is_content(lines[n - 1])), None)
            if target is None:
                result.malformed.append((number, comment.strip()))
                continue
        else:
            target = None
        result.items.append(Suppression(kind, number, target, codes))
    return result


def apply_suppressions(issues: list, suppressions: Suppressions) -> Tuple[list, list, Set[Suppression]]:
    """Split ``issues`` into (kept, suppressed) and return the suppressions that were used."""
    kept, suppressed = [], []
    used: Set[Suppression] = set()
    for issue in issues:
        s = suppressions.match(issue.code, issue.line)
        if s is None:
            kept.append(issue)
        else:
            suppressed.append(issue)
            used.add(s)
    return kept, suppressed, used


def unknown_codes(suppressions: Suppressions, known: Dict[str, object]) -> List[Tuple[Suppression, str]]:
    """``(suppression, code)`` pairs naming a code the linter does not have."""
    return [(s, c) for s in suppressions.items for c in s.codes if c != ALL and c not in known]
