"""robots-txt-lab: a robots.txt parser, tester, linter and differ.

Follows RFC 9309 (Robots Exclusion Protocol) and Google's documented
interpretation of it.
"""

from ._version import __version__
from .agents import agent_profile, crawler_token, product_token
from .diff import DiffResult, diff
from .encoding import normalize_path, normalize_pattern, request_path
from .fetch import FetchResult, RawResponse, TransportError, fetch
from .lint import CHECKS, Issue, LintReport, lint, lint_report
from .matcher import best_rule, pattern_matches
from .models import Directive, Group, RobotsTxt, Rule
from .parser import MAX_BYTES, parse, parse_file
from .robots import Robots, Verdict
from .scope import in_scope, robots_url
from .sitemaps import sitemap_problems
from .suppress import Suppression, Suppressions, parse_suppressions

__all__ = [
    "CHECKS",
    "MAX_BYTES",
    "DiffResult",
    "Directive",
    "FetchResult",
    "Group",
    "Issue",
    "LintReport",
    "RawResponse",
    "Robots",
    "RobotsTxt",
    "Rule",
    "Suppression",
    "Suppressions",
    "TransportError",
    "Verdict",
    "__version__",
    "agent_profile",
    "best_rule",
    "crawler_token",
    "diff",
    "fetch",
    "in_scope",
    "lint",
    "lint_report",
    "normalize_path",
    "normalize_pattern",
    "parse",
    "parse_file",
    "parse_suppressions",
    "pattern_matches",
    "product_token",
    "request_path",
    "robots_url",
    "sitemap_problems",
]
