"""Fetching robots.txt and turning the HTTP outcome into a policy.

=================  ======================================================
Fetch outcome      Effect
=================  ======================================================
2xx                The body is parsed and its rules apply.
3xx                Redirects are followed, up to 5 hops by default (RFC
                   9309: at least five). Beyond that the file is treated
                   as unavailable, as Google treats it like a 404.
4xx                Unavailable: crawlers may access everything. In the
                   ``google`` profile 429 is the exception and is handled
                   like a server error.
5xx                Unreachable: complete disallow. Google stops crawling
                   for 12 hours, then uses a cached copy for up to 30
                   days; no cache is available here, so the result is a
                   complete disallow.
network errors     Unreachable (DNS failures, timeouts, resets).
=================  ======================================================
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from ._version import __version__
from .parser import MAX_BYTES
from .robots import Robots
from .scope import robots_url

DEFAULT_USER_AGENT = f"robots-txt-lab/{__version__} (+https://github.com/saizul/robots-txt-lab)"
MAX_REDIRECTS = 5

OUTCOME_OK = "ok"
OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_UNREACHABLE = "unreachable"


@dataclass
class RawResponse:
    status: int
    headers: Dict[str, str]
    body: bytes
    url: str


#: (url, request headers, timeout seconds, max body bytes) -> response. Must not follow redirects.
Transport = Callable[[str, Dict[str, str], float, int], RawResponse]


class TransportError(Exception):
    """The request failed before an HTTP status was received."""


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status: Optional[int]
    outcome: str
    reason: str
    robots: Robots
    body: bytes = b""
    #: Every hop: (url, status or None on a network error).
    chain: List[Tuple[str, Optional[int]]] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)

    @property
    def redirects(self) -> int:
        return max(0, len(self.chain) - 1)

    def to_dict(self) -> dict:
        parsed = self.robots.parsed
        return {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "status": self.status,
            "outcome": self.outcome,
            "access": self.robots.access,
            "reason": self.reason,
            "redirects": self.redirects,
            "chain": [{"url": u, "status": s} for u, s in self.chain],
            "content_type": self.headers.get("content-type"),
            "size_bytes": len(self.body),
            "truncated": parsed.truncated,
            "groups": len(parsed.groups),
            "sitemaps": parsed.sitemap_urls,
        }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urllib_transport(url: str, headers: Dict[str, str], timeout: float, max_bytes: int) -> RawResponse:
    """Default transport built on urllib; redirects are returned, not followed."""
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener.open(request, timeout=timeout) as resp:
            body = resp.read(max_bytes + 1)
            return RawResponse(resp.status, {k.lower(): v for k, v in resp.headers.items()}, body, resp.geturl())
    except urllib.error.HTTPError as err:
        try:
            body = err.read(max_bytes + 1)
        except Exception:
            body = b""
        hdrs = {k.lower(): v for k, v in (err.headers.items() if err.headers else [])}
        return RawResponse(err.code, hdrs, body, url)
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as err:
        reason = getattr(err, "reason", err)
        raise TransportError(str(reason)) from err


def classify_status(status: int, profile: str = "google") -> str:
    if 200 <= status < 300:
        return OUTCOME_OK
    if status == 429 and profile == "google":
        return OUTCOME_UNREACHABLE
    if 400 <= status < 500:
        return OUTCOME_UNAVAILABLE
    return OUTCOME_UNREACHABLE


def _robots_for(outcome: str, reason: str, body: bytes, profile: str, max_bytes: int) -> Robots:
    if outcome == OUTCOME_OK:
        return Robots.from_text(body, profile=profile, max_bytes=max_bytes)
    if outcome == OUTCOME_UNAVAILABLE:
        return Robots.allow_all(reason, profile)
    return Robots.disallow_all(reason, profile)


def fetch(
    url: str,
    *,
    profile: str = "google",
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 10.0,
    max_redirects: int = MAX_REDIRECTS,
    max_bytes: int = MAX_BYTES,
    transport: Optional[Transport] = None,
) -> FetchResult:
    """Fetch the robots.txt for ``url`` (a site URL or a robots.txt URL).

    Any URL is accepted; the robots.txt location is derived from its scheme,
    host and port, so ``fetch("https://example.com/some/page")`` fetches
    ``https://example.com/robots.txt``.
    """
    send = transport or urllib_transport
    start = robots_url(url)
    current = start
    chain: List[Tuple[str, Optional[int]]] = []
    headers = {"User-Agent": user_agent, "Accept": "text/plain, */*;q=0.1"}

    for _hop in range(max_redirects + 1):
        try:
            resp = send(current, headers, timeout, max_bytes)
        except TransportError as err:
            chain.append((current, None))
            reason = f"network error: {err}"
            return FetchResult(
                start,
                current,
                None,
                OUTCOME_UNREACHABLE,
                reason,
                Robots.disallow_all(reason, profile),
                chain=chain,
            )
        chain.append((current, resp.status))
        if 300 <= resp.status < 400:
            location = resp.headers.get("location")
            if not location:
                reason = f"HTTP {resp.status} without a Location header"
                return FetchResult(
                    start,
                    current,
                    resp.status,
                    OUTCOME_UNAVAILABLE,
                    reason,
                    Robots.allow_all(reason, profile),
                    chain=chain,
                    headers=resp.headers,
                )
            current = urljoin(current, location.strip())
            continue
        outcome = classify_status(resp.status, profile)
        reason = f"HTTP {resp.status}"
        if outcome == OUTCOME_UNREACHABLE and resp.status == 429:
            reason = "HTTP 429 (Google treats it like a server error)"
        return FetchResult(
            start,
            current,
            resp.status,
            outcome,
            reason,
            _robots_for(outcome, reason, resp.body, profile, max_bytes),
            body=resp.body if outcome == OUTCOME_OK else b"",
            chain=chain,
            headers=resp.headers,
        )

    reason = f"more than {max_redirects} redirects"
    return FetchResult(
        start,
        current,
        chain[-1][1] if chain else None,
        OUTCOME_UNAVAILABLE,
        reason,
        Robots.allow_all(reason, profile),
        chain=chain,
    )
