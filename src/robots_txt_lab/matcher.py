"""Rule matching: wildcards, specificity and allow-wins-ties.

``*`` matches any sequence of octets (including ``/``) and ``$`` at the very
end of a pattern anchors it to the end of the path. A ``$`` anywhere else is
an ordinary character. Matching starts at the first octet of the path and is
case-sensitive.

The algorithm tracks the set of path positions the pattern prefix can end at,
which is linear in ``len(path) * len(pattern)`` and immune to the exponential
backtracking a naive regular expression translation can hit.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .models import Rule


def pattern_matches(pattern: str, path: str) -> bool:
    """True when the normalised ``pattern`` matches the normalised ``path``."""
    n = len(path)
    last = len(pattern) - 1
    # Sorted, de-duplicated positions in ``path`` reachable so far.
    positions = [0]
    for i, ch in enumerate(pattern):
        if ch == "$" and i == last:
            return positions[-1] == n
        if ch == "*":
            positions = list(range(positions[0], n + 1))
            continue
        nxt = [p + 1 for p in positions if p < n and path[p] == ch]
        if not nxt:
            return False
        positions = nxt
    return True


def best_rule(rules: Iterable[Rule], path: str) -> Optional[Rule]:
    """The deciding rule for ``path``: longest pattern wins, ``allow`` wins ties.

    Returns ``None`` when no rule matches.
    """
    best: Optional[Rule] = None
    for rule in rules:
        if not pattern_matches(rule.pattern, path):
            continue
        if (
            best is None
            or rule.priority > best.priority
            or (rule.priority == best.priority and rule.allow and not best.allow)
        ):
            best = rule
    return best


def literal_prefix(pattern: str) -> str:
    """The part of a pattern before its first wildcard."""
    cut = len(pattern)
    for i, ch in enumerate(pattern):
        if ch == "*" or (ch == "$" and i == len(pattern) - 1):
            cut = i
            break
    return pattern[:cut]
