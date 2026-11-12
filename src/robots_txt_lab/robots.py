"""High-level API: decide whether a crawler may fetch a URL.

>>> from robots_txt_lab import Robots
>>> robots = Robots.from_text("User-agent: *\\nDisallow: /private/\\n")
>>> robots.allowed("https://example.com/private/x", "Googlebot")
False
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Union

from .agents import AgentProfile, agent_profile
from .encoding import request_path
from .matcher import best_rule
from .models import Group, RobotsTxt, Rule
from .parser import MAX_BYTES, parse

#: Whole-file states that come from the fetch result rather than the content.
ACCESS_PARSED = "parsed"
ACCESS_ALLOW_ALL = "allow-all"  # 4xx (unavailable): no restrictions
ACCESS_DISALLOW_ALL = "disallow-all"  # 5xx / network error (unreachable): complete disallow


@dataclass(frozen=True)
class Verdict:
    url: str
    user_agent: str
    allowed: bool
    #: Normalised path (with query) the rules were matched against.
    path: str
    #: Product token whose group was used, ``"*"``, or ``None`` when no group applied.
    group_token: Optional[str]
    #: First line of each group that was merged into the applicable group.
    group_lines: tuple = ()
    rule: Optional[Rule] = None
    #: matched-allow, matched-disallow, no-matching-rule, no-matching-group,
    #: robots-txt-always-allowed, unavailable-allow-all, unreachable-disallow-all
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "user_agent": self.user_agent,
            "allowed": self.allowed,
            "path": self.path,
            "group": self.group_token,
            "group_lines": list(self.group_lines),
            "rule": None
            if self.rule is None
            else {"directive": self.rule.directive, "path": self.rule.path, "line": self.rule.line},
            "reason": self.reason,
        }


@dataclass
class Robots:
    """A parsed robots.txt plus how it was obtained, ready for queries."""

    parsed: RobotsTxt = field(default_factory=RobotsTxt)
    profile: str = "google"
    access: str = ACCESS_PARSED
    #: Why ``access`` is not ``parsed`` (for example "HTTP 503").
    access_reason: str = ""

    @classmethod
    def from_text(cls, content: Union[str, bytes], *, profile: str = "google", max_bytes: int = MAX_BYTES) -> Robots:
        return cls(parse(content, profile=profile, max_bytes=max_bytes), profile)

    @classmethod
    def allow_all(cls, reason: str, profile: str = "google") -> Robots:
        return cls(RobotsTxt(), profile, ACCESS_ALLOW_ALL, reason)

    @classmethod
    def disallow_all(cls, reason: str, profile: str = "google") -> Robots:
        return cls(RobotsTxt(), profile, ACCESS_DISALLOW_ALL, reason)

    # -- group selection -------------------------------------------------

    def select_groups(self, agent: AgentProfile) -> tuple[Optional[str], List[Group]]:
        """Groups that apply to ``agent``: every group naming the first token
        in its chain that has any group (merged), else the ``*`` groups."""
        for token in agent.tokens:
            groups = self.parsed.groups_for_token(token)
            if groups:
                return token, groups
        if agent.use_global:
            groups = self.parsed.groups_for_token("*")
            if groups:
                return "*", groups
        return None, []

    def rules_for(self, user_agent: str) -> List[Rule]:
        _, groups = self.select_groups(agent_profile(user_agent, self.profile))
        return [r for g in groups for r in g.rules]

    # -- verdicts ------------------------------------------------------------

    def check(self, url: str, user_agent: str) -> Verdict:
        path = request_path(url)
        if self.access == ACCESS_ALLOW_ALL:
            return Verdict(url, user_agent, True, path, None, reason="unavailable-allow-all")
        if self.access == ACCESS_DISALLOW_ALL:
            return Verdict(url, user_agent, False, path, None, reason="unreachable-disallow-all")
        if path == "/robots.txt":
            return Verdict(url, user_agent, True, path, None, reason="robots-txt-always-allowed")
        agent = agent_profile(user_agent, self.profile)
        token, groups = self.select_groups(agent)
        if not groups:
            return Verdict(url, user_agent, True, path, None, reason="no-matching-group")
        lines = tuple(g.start_line for g in groups)
        rule = best_rule((r for g in groups for r in g.rules), path)
        if rule is None:
            return Verdict(url, user_agent, True, path, token, lines, None, "no-matching-rule")
        reason = "matched-allow" if rule.allow else "matched-disallow"
        return Verdict(url, user_agent, rule.allow, path, token, lines, rule, reason)

    def allowed(self, url: str, user_agent: str) -> bool:
        return self.check(url, user_agent).allowed

    def check_many(self, urls: Iterable[str], user_agents: Iterable[str]) -> List[Verdict]:
        agents = list(user_agents)
        return [self.check(u, a) for u in urls for a in agents]

    @property
    def sitemaps(self) -> List[str]:
        return self.parsed.sitemap_urls
