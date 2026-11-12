"""Compare two robots.txt versions: rule changes and URL verdict changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .matcher import literal_prefix
from .models import RobotsTxt
from .robots import Robots, Verdict

DEFAULT_AGENTS = ("Googlebot", "Bingbot", "*")


@dataclass(frozen=True)
class RuleChange:
    #: Sorted product tokens of the group, joined with ", ".
    agents: str
    change: str  # "added" or "removed"
    directive: str
    path: str
    line: int

    def to_dict(self) -> dict:
        return {
            "agents": self.agents,
            "change": self.change,
            "directive": self.directive,
            "path": self.path,
            "line": self.line,
        }


@dataclass(frozen=True)
class VerdictChange:
    url: str
    user_agent: str
    before: Verdict
    after: Verdict

    @property
    def direction(self) -> str:
        return "now-allowed" if self.after.allowed else "now-disallowed"

    def to_dict(self) -> dict:
        def rule(v: Verdict) -> Optional[str]:
            return None if v.rule is None else f"{v.rule} (line {v.rule.line})"

        return {
            "url": self.url,
            "user_agent": self.user_agent,
            "change": self.direction,
            "before": {"allowed": self.before.allowed, "rule": rule(self.before), "reason": self.before.reason},
            "after": {"allowed": self.after.allowed, "rule": rule(self.after), "reason": self.after.reason},
        }


@dataclass
class DiffResult:
    rule_changes: List[RuleChange] = field(default_factory=list)
    sitemaps_added: List[str] = field(default_factory=list)
    sitemaps_removed: List[str] = field(default_factory=list)
    verdict_changes: List[VerdictChange] = field(default_factory=list)
    urls_tested: List[str] = field(default_factory=list)
    agents_tested: List[str] = field(default_factory=list)
    #: True when the URLs were derived from the rules because none were given.
    derived_urls: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.rule_changes or self.sitemaps_added or self.sitemaps_removed or self.verdict_changes)

    def to_dict(self) -> dict:
        return {
            "changed": self.changed,
            "rule_changes": [c.to_dict() for c in self.rule_changes],
            "sitemaps_added": self.sitemaps_added,
            "sitemaps_removed": self.sitemaps_removed,
            "verdict_changes": [c.to_dict() for c in self.verdict_changes],
            "urls_tested": len(self.urls_tested),
            "agents_tested": self.agents_tested,
            "derived_urls": self.derived_urls,
        }


def _rule_index(robots: RobotsTxt) -> Dict[Tuple[str, str, str], int]:
    """(agents, directive, normalised pattern) -> first line, with groups merged per agent set."""
    index: Dict[Tuple[str, str, str], int] = {}
    for group in robots.groups:
        agents = ", ".join(sorted(set(group.tokens))) or "?"
        for rule in group.rules:
            index.setdefault((agents, rule.directive, rule.pattern), rule.line)
    return index


def _paths(robots: RobotsTxt) -> Dict[Tuple[str, str, str], str]:
    out: Dict[Tuple[str, str, str], str] = {}
    for group in robots.groups:
        agents = ", ".join(sorted(set(group.tokens))) or "?"
        for rule in group.rules:
            out.setdefault((agents, rule.directive, rule.pattern), rule.path)
    return out


def derive_test_urls(*files: RobotsTxt) -> List[str]:
    """Probe paths built from the rules of both files: each rule's literal prefix,
    a page under it, and the same with typical suffixes for wildcard rules."""
    paths = {"/"}
    for robots in files:
        for group in robots.groups:
            for rule in group.rules:
                prefix = literal_prefix(rule.pattern)
                if not prefix.startswith("/"):
                    prefix = "/" + prefix
                paths.add(prefix)
                child = prefix + ("page" if prefix.endswith("/") else "/page")
                paths.add(child)
                tail = rule.pattern[len(literal_prefix(rule.pattern)) :].lstrip("*").rstrip("$")
                if tail and "*" not in tail:
                    paths.add((prefix if prefix.endswith("/") else prefix + "/") + "x" + tail)
    return sorted(paths)


def diff(
    old: Robots,
    new: Robots,
    urls: Optional[Iterable[str]] = None,
    agents: Sequence[str] = DEFAULT_AGENTS,
) -> DiffResult:
    result = DiffResult(agents_tested=list(agents))
    before, after = _rule_index(old.parsed), _rule_index(new.parsed)
    before_paths, after_paths = _paths(old.parsed), _paths(new.parsed)
    for key in sorted(set(before) - set(after)):
        result.rule_changes.append(RuleChange(key[0], "removed", key[1], before_paths[key], before[key]))
    for key in sorted(set(after) - set(before)):
        result.rule_changes.append(RuleChange(key[0], "added", key[1], after_paths[key], after[key]))

    old_maps, new_maps = old.parsed.sitemap_urls, new.parsed.sitemap_urls
    result.sitemaps_added = [u for u in new_maps if u not in old_maps]
    result.sitemaps_removed = [u for u in old_maps if u not in new_maps]

    url_list = list(urls) if urls is not None else []
    if not url_list:
        url_list = derive_test_urls(old.parsed, new.parsed)
        result.derived_urls = True
    result.urls_tested = url_list
    for url in url_list:
        for agent in agents:
            a, b = old.check(url, agent), new.check(url, agent)
            if a.allowed != b.allowed:
                result.verdict_changes.append(VerdictChange(url, agent, a, b))
    return result
