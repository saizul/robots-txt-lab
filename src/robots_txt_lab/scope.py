"""Which robots.txt governs a URL.

A robots.txt file applies only to the scheme, host and port it is served from
(Google, "File location and range of validity"). Default ports are
equivalent to no port, host names are case-insensitive, and internationalised
domain names are equivalent to their punycode form.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

DEFAULT_PORTS = {"http": 80, "https": 443, "ftp": 21}


class ScopeError(ValueError):
    """The URL cannot have a robots.txt (no scheme or host)."""


def _host(hostname: str) -> str:
    host = hostname.rstrip(".").lower()
    if host.startswith("["):  # IPv6 literal
        return host
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def origin_of(url: str) -> tuple[str, str, Optional[int]]:
    """(scheme, punycode host, port or None for the default port)."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if not scheme or not parts.hostname:
        raise ScopeError(f"not an absolute URL: {url!r}")
    try:
        port = parts.port
    except ValueError as exc:
        raise ScopeError(f"invalid port in {url!r}") from exc
    if port is not None and DEFAULT_PORTS.get(scheme) == port:
        port = None
    hostname = parts.hostname
    if ":" in hostname:  # urlsplit strips brackets from IPv6 hosts
        hostname = f"[{hostname}]"
    return scheme, _host(hostname), port


def robots_url(url: str) -> str:
    """The robots.txt URL that governs ``url``.

    >>> robots_url("https://Example.com:443/folder/page?x=1")
    'https://example.com/robots.txt'
    """
    scheme, host, port = origin_of(url)
    netloc = host if port is None else f"{host}:{port}"
    return f"{scheme}://{netloc}/robots.txt"


def in_scope(robots_txt_url: str, url: str) -> bool:
    """True when ``url`` is governed by the robots.txt at ``robots_txt_url``."""
    try:
        return origin_of(robots_txt_url) == origin_of(url)
    except ScopeError:
        return False


def is_valid_robots_location(url: str) -> bool:
    """robots.txt must be at the top level: ``/robots.txt`` exactly."""
    try:
        origin_of(url)
    except ScopeError:
        return False
    return urlsplit(url).path == "/robots.txt"
