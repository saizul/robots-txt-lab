"""Sitemap extraction and validation.

A ``sitemap`` line holds the absolute URL of a sitemap or sitemap index. It is
not tied to any group, may point to another host, and there can be any number
of them (sitemaps.org; Google robots.txt documentation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlsplit

from .models import Directive, RobotsTxt
from .scope import ScopeError, origin_of


@dataclass(frozen=True)
class SitemapProblem:
    line: int
    url: str
    kind: str
    message: str


def sitemap_problems(robots: RobotsTxt, robots_url: Optional[str] = None) -> List[SitemapProblem]:
    """Check every ``sitemap`` line. ``robots_url`` enables the cross-host note."""
    problems: List[SitemapProblem] = []
    seen: dict[str, int] = {}
    for d in robots.sitemaps:
        if d.value and d.value in seen:
            problems.append(SitemapProblem(d.line, d.value, "sitemap-duplicate", f"duplicate of line {seen[d.value]}"))
            continue
        seen[d.value] = d.line
        problems.extend(check_sitemap(d, robots_url))
        raw = robots.lines[d.line - 1] if 0 < d.line <= len(robots.lines) else ""
        cut = raw.find("#")
        if cut > 0 and not raw[cut - 1].isspace():
            problems.append(
                SitemapProblem(
                    d.line,
                    d.value,
                    "sitemap-hash",
                    "'#' starts a comment, so the URL was cut before it",
                )
            )
    return problems


def check_sitemap(d: Directive, robots_url: Optional[str] = None) -> List[SitemapProblem]:
    url = d.value
    if not url:
        return [SitemapProblem(d.line, url, "sitemap-empty", "sitemap line without a URL")]
    if any(c in url for c in " \t"):
        return [SitemapProblem(d.line, url, "sitemap-invalid-url", "the URL contains whitespace")]
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return [
            SitemapProblem(
                d.line,
                url,
                "sitemap-not-absolute",
                "sitemap URLs must be absolute, including the protocol and host",
            )
        ]
    if parts.scheme.lower() not in ("http", "https"):
        return [SitemapProblem(d.line, url, "sitemap-bad-scheme", f"unsupported scheme {parts.scheme!r}")]
    out: List[SitemapProblem] = []
    if robots_url:
        try:
            if origin_of(url)[1] != origin_of(robots_url)[1]:
                out.append(
                    SitemapProblem(
                        d.line,
                        url,
                        "sitemap-cross-host",
                        "the sitemap is on another host (allowed: a sitemap listed in robots.txt "
                        "does not have to be on the same host)",
                    )
                )
            elif origin_of(url)[0] != origin_of(robots_url)[0]:
                out.append(
                    SitemapProblem(d.line, url, "sitemap-scheme-mismatch", "the sitemap uses a different protocol")
                )
        except ScopeError:
            pass
    return out
