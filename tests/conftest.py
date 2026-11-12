from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pytest

from robots_txt_lab import Robots
from robots_txt_lab.fetch import RawResponse, TransportError


def robots(text: str, profile: str = "google") -> Robots:
    return Robots.from_text(text, profile=profile)


class FakeTransport:
    """Serves canned responses by URL and records requests."""

    def __init__(self, routes: Dict[str, Tuple[int, Dict[str, str], bytes]], errors: Optional[Dict[str, str]] = None):
        self.routes = routes
        self.errors = errors or {}
        self.requests: List[Tuple[str, Dict[str, str]]] = []

    def __call__(self, url: str, headers: Dict[str, str], timeout: float, max_bytes: int) -> RawResponse:
        self.requests.append((url, dict(headers)))
        if url in self.errors:
            raise TransportError(self.errors[url])
        if url not in self.routes:
            return RawResponse(404, {}, b"not found", url)
        status, hdrs, body = self.routes[url]
        return RawResponse(status, {k.lower(): v for k, v in hdrs.items()}, body[: max_bytes + 1], url)


@pytest.fixture
def rfc_simple() -> str:
    # RFC 9309 section 5.1
    return (
        "User-Agent: *\n"
        "Disallow: *.gif$\n"
        "Disallow: /example/\n"
        "Allow: /publications/\n"
        "\n"
        "User-Agent: foobot\n"
        "Disallow:/\n"
        "Allow:/example/page.html\n"
        "Allow:/example/allowed.gif\n"
        "\n"
        "User-Agent: barbot\n"
        "User-Agent: bazbot\n"
        "Disallow: /example/page.html\n"
        "\n"
        "User-Agent: quxbot\n"
        "\n"
        "EOF\n"
    )
