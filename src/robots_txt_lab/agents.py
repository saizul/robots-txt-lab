"""User-agent product tokens and crawler profiles.

A ``user-agent`` line in robots.txt names a *product token*: letters, ``_``
and ``-`` only (RFC 9309 section 2.2.1). Google ignores everything after the
token, so ``googlebot/1.2`` and ``googlebot*`` both mean ``googlebot``.
Matching is case-insensitive.

Some Google crawlers answer to more than one token. Googlebot-Image, for
example, follows a ``Googlebot-Image`` group if there is one and otherwise the
``Googlebot`` group. A few special-case crawlers (AdsBot, Mediapartners) ignore
the ``*`` group. Those behaviours are applied in the ``google`` profile only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN = re.compile(r"[A-Za-z_-]+")

#: Google crawlers that fall back to another token's group (most specific first).
GOOGLE_FALLBACKS: dict[str, tuple[str, ...]] = {
    "googlebot-image": ("googlebot",),
    "googlebot-video": ("googlebot",),
    "googlebot-news": ("googlebot",),
    "google-inspectiontool": ("googlebot",),
    "googleother-image": ("googleother",),
    "googleother-video": ("googleother",),
}

#: Google crawlers documented to ignore the global ``*`` group.
GOOGLE_IGNORES_GLOBAL: frozenset[str] = frozenset(
    {
        "adsbot-google",
        "adsbot-google-mobile",
        "adsbot-google-mobile-apps",
        "mediapartners-google",
        "apis-google",
        "duplexweb-google",
    }
)

# Product names in browser-style user agent strings that are never crawlers.
_BROWSER_PRODUCTS = frozenset(
    {
        "mozilla",
        "applewebkit",
        "khtml",
        "like",
        "gecko",
        "chrome",
        "safari",
        "version",
        "mobile",
        "compatible",
        "linux",
        "android",
        "windows",
        "macintosh",
        "intel",
        "mac",
        "os",
        "x",
        "u",
        "build",
        "edg",
        "firefox",
        "opr",
        "iphone",
        "cpu",
        "wow",
        "win",
        "nt",
        "http",
        "https",
        "www",
    }
)

#: Well-known crawler tokens, used to pick the token out of a full UA string.
KNOWN_TOKENS: tuple[str, ...] = (
    "Googlebot-Image",
    "Googlebot-Video",
    "Googlebot-News",
    "Googlebot",
    "Storebot-Google",
    "Google-InspectionTool",
    "GoogleOther-Image",
    "GoogleOther-Video",
    "GoogleOther",
    "Google-Extended",
    "Google-CloudVertexBot",
    "AdsBot-Google-Mobile",
    "AdsBot-Google",
    "Mediapartners-Google",
    "APIs-Google",
    "Bingbot",
    "BingPreview",
    "AdIdxBot",
    "MSNBot",
    "Slurp",
    "DuckDuckBot",
    "Baiduspider",
    "YandexBot",
    "Yandex",
    "Applebot-Extended",
    "Applebot",
    "GPTBot",
    "OAI-SearchBot",
    "CCBot",
    "PerplexityBot",
    "Bytespider",
    "Amazonbot",
    "facebookexternalhit",
    "Twitterbot",
    "LinkedInBot",
    "AhrefsBot",
    "SemrushBot",
    "MJ12bot",
    "DotBot",
    "PetalBot",
    "SeznamBot",
)


def product_token(value: str) -> str:
    """The product token a ``user-agent`` line value stands for, lower-cased.

    ``"*"`` (alone, or followed by whitespace) stays ``"*"``. Returns ``""``
    when the value has no valid token, for example ``"*bot"`` or ``"/x"``.
    """
    value = value.strip()
    if value == "*" or (value.startswith("*") and value[1:2].isspace()):
        return "*"
    m = _TOKEN.match(value)
    return m.group(0).lower() if m else ""


def is_valid_token(value: str) -> bool:
    """True when the whole value is a valid product token (or ``*``)."""
    value = value.strip()
    return value == "*" or bool(_TOKEN.fullmatch(value))


def crawler_token(user_agent: str) -> str:
    """Find the product token in what the user passed for a crawler.

    A bare token (``Googlebot``) is used as is. For a full HTTP user agent
    string the first well-known crawler token found in it wins, then the first
    product that is not a browser component.
    """
    ua = user_agent.strip()
    if _TOKEN.fullmatch(ua):
        return ua.lower()
    lower = ua.lower()
    for token in KNOWN_TOKENS:
        if re.search(rf"(?<![A-Za-z_-]){re.escape(token.lower())}(?![A-Za-z_-])", lower):
            return token.lower()
    for m in _TOKEN.finditer(ua):
        candidate = m.group(0)
        if candidate.lower() not in _BROWSER_PRODUCTS and len(candidate) > 1:
            return candidate.lower()
    return product_token(ua)


@dataclass(frozen=True)
class AgentProfile:
    """How one crawler picks its group."""

    token: str
    #: Tokens to try in order; the first one with a matching group wins.
    tokens: tuple[str, ...] = field(default_factory=tuple)
    #: Whether the ``*`` group applies when no specific group matches.
    use_global: bool = True


def agent_profile(user_agent: str, profile: str = "google") -> AgentProfile:
    token = crawler_token(user_agent)
    if profile == "google":
        chain = (token, *GOOGLE_FALLBACKS.get(token, ()))
        return AgentProfile(token, chain, token not in GOOGLE_IGNORES_GLOBAL)
    return AgentProfile(token, (token,), True)
