"""robots.txt parser following RFC 9309 and Google's documented behaviour.

* Lines end in CR, LF or CRLF. A UTF-8 byte order mark at the start is ignored.
* Content beyond the size limit (500 KiB by default) is ignored.
* ``#`` starts a comment; leading and trailing whitespace is ignored.
* Keys are case-insensitive. In the ``google`` profile common misspellings
  (``dissallow``, ``useragent``, ``site-map`` ...) and a missing colon
  (``disallow /x``) are accepted, as Google's parser does.
* A group is one or more ``user-agent`` lines followed by rules; a
  ``user-agent`` line after a rule starts a new group. Other lines, such as
  ``sitemap`` or unknown keys, never end a group.
* Rules before the first ``user-agent`` line belong to no group and are ignored.
* ``allow`` / ``disallow`` with an empty value are ignored.
"""

from __future__ import annotations

import re
from typing import Optional, Union

from .agents import product_token
from .encoding import normalize_pattern
from .models import Directive, Group, ParseNote, RobotsTxt, Rule

#: Google's limit, and the minimum RFC 9309 allows a crawler to impose.
MAX_BYTES = 500 * 1024

BOM = b"\xef\xbb\xbf"

_CANONICAL = {
    "user-agent": "user-agent",
    "allow": "allow",
    "disallow": "disallow",
    "sitemap": "sitemap",
}

#: Misspellings Google's open-source parser accepts.
TYPOS = {
    "useragent": "user-agent",
    "user agent": "user-agent",
    "user_agent": "user-agent",
    "dissallow": "disallow",
    "dissalow": "disallow",
    "disalow": "disallow",
    "diasllow": "disallow",
    "disallaw": "disallow",
    "site-map": "sitemap",
}

_LINE_SPLIT = re.compile(r"\r\n|\r|\n")
_WS = " \t"

PROFILES = ("google", "rfc")


def _canonical_key(raw: str, profile: str) -> tuple[str, bool]:
    """Map a raw key to its canonical name; the flag says whether it was a typo."""
    key = " ".join(raw.strip().lower().split())
    if key in _CANONICAL:
        return key, False
    if profile == "google" and key in TYPOS:
        return TYPOS[key], True
    return key, False


def decode(data: bytes, max_bytes: int = MAX_BYTES) -> tuple[str, dict[str, bool]]:
    """Decode raw robots.txt bytes: strip a BOM, apply the size limit, decode UTF-8."""
    flags = {"had_bom": False, "truncated": False, "decode_errors": False}
    if data.startswith(BOM):
        data = data[len(BOM) :]
        flags["had_bom"] = True
    if max_bytes and len(data) > max_bytes:
        data = data[:max_bytes]
        flags["truncated"] = True
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        flags["decode_errors"] = True
    return text, flags


def parse(
    content: Union[str, bytes],
    *,
    profile: str = "google",
    max_bytes: int = MAX_BYTES,
) -> RobotsTxt:
    """Parse robots.txt content (``bytes`` as fetched, or ``str``)."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; use one of {', '.join(PROFILES)}")
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    robots = RobotsTxt(size_bytes=len(data))
    if isinstance(content, str) and content.startswith("﻿"):
        data = content.encode("utf-8")
    text, flags = decode(data, max_bytes)
    robots.had_bom = flags["had_bom"]
    robots.truncated = flags["truncated"]
    robots.decode_errors = flags["decode_errors"]
    if text.startswith("﻿"):  # a BOM inside a str that was not at byte level
        text = text[1:]
        robots.had_bom = True

    lines = _LINE_SPLIT.split(text)
    if lines and lines[-1] == "":
        lines.pop()
    robots.lines = lines

    current: Optional[Group] = None
    seen_rule = False

    for number, raw in enumerate(lines, start=1):
        line = raw.split("#", 1)[0].strip(_WS)
        if not line:
            continue

        key_raw, sep, value = line.partition(":")
        if not sep:
            # Google accepts "key value" when the colon is missing.
            parts = line.split(None, 1)
            key, _ = _canonical_key(parts[0], profile)
            if profile == "google" and len(parts) == 2 and key in _CANONICAL:
                key_raw, value = parts
                robots.notes.append(ParseNote("missing-colon", number, raw))
            else:
                robots.notes.append(ParseNote("invalid-line", number, raw))
                continue
        value = value.strip(_WS)
        key, typo = _canonical_key(key_raw, profile)
        robots.keys.append((number, key_raw.strip(_WS), key))
        if typo:
            robots.notes.append(ParseNote("typo", number, raw, f"{key_raw.strip()} -> {key}"))

        if key == "user-agent":
            if current is None or seen_rule:
                current = Group(start_line=number)
                robots.groups.append(current)
                seen_rule = False
            token = product_token(value)
            current.agents.append(value)
            current.agent_lines.append(number)
            if token:
                current.tokens.append(token)
            else:
                robots.notes.append(ParseNote("invalid-user-agent", number, raw))
        elif key in ("allow", "disallow"):
            if current is None:
                robots.notes.append(ParseNote("rule-outside-group", number, raw))
                continue
            seen_rule = True
            if not value:
                current.empty_rules.append(number)
                continue
            current.rules.append(Rule(key == "allow", value, normalize_pattern(value), number))
        else:
            group_index = len(robots.groups) - 1 if current is not None else None
            directive = Directive(key, key_raw.strip(_WS), value, number, group_index)
            if key == "sitemap":
                robots.sitemaps.append(directive)
            else:
                robots.others.append(directive)

    return robots


def parse_file(path: str, *, profile: str = "google", max_bytes: int = MAX_BYTES) -> RobotsTxt:
    with open(path, "rb") as fh:
        return parse(fh.read(), profile=profile, max_bytes=max_bytes)
