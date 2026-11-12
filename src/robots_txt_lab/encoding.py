"""Percent-encoding normalisation for robots.txt matching (RFC 9309 section 2.2.2).

Both the rule paths and the request URI are brought to one canonical form
before comparison:

* octets outside printable ASCII (UTF-8 bytes of non-ASCII characters,
  control characters and space) are percent-encoded;
* existing percent escapes get upper-case hex digits;
* an escape of an *unreserved* character (``A-Z a-z 0-9 - . _ ~``) is decoded,
  so ``/foo/bar/%62%61%7A`` and ``/foo/bar/baz`` compare equal;
* escapes of reserved characters (``%2F``, ``%3F``, ``%2A`` ...) stay encoded,
  so an encoded slash never matches a real one.

In a rule path ``*`` and a trailing ``$`` are wildcards. In a URI they are
ordinary characters, and they are encoded as ``%2A`` and ``%24`` so that a
rule can match them literally by writing the escape, as RFC 9309 shows::

    Disallow: /path/file-with-a-%2A.html    matches  /path/file-with-a-*.html
"""

from __future__ import annotations

import re
import string

UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
_HEX = frozenset("0123456789abcdefABCDEF")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

# Printable ASCII that is not valid in a URI and is therefore always escaped.
_ALWAYS_ESCAPE = frozenset('"<>\\^`{|}')


def _escape_byte(b: int) -> str:
    return f"%{b:02X}"


def normalize(value: str, *, is_pattern: bool) -> str:
    """Return the canonical percent-encoded form of a rule path or URI path."""
    data = value.encode("utf-8", errors="surrogatepass")
    out: list[str] = []
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0x25:  # '%'
            if i + 2 < n and chr(data[i + 1]) in _HEX and chr(data[i + 2]) in _HEX:
                octet = int(data[i + 1 : i + 3].decode("ascii"), 16)
                ch = chr(octet)
                out.append(ch if octet < 0x80 and ch in UNRESERVED else _escape_byte(octet))
                i += 3
                continue
            # A lone '%' is not a valid escape; encode it so it compares literally.
            out.append("%25")
            i += 1
            continue
        if b >= 0x80 or b <= 0x20 or b == 0x7F:
            out.append(_escape_byte(b))
        else:
            ch = chr(b)
            if ch in _ALWAYS_ESCAPE:
                out.append(_escape_byte(b))
            elif not is_pattern and ch == "*":
                out.append("%2A")
            elif not is_pattern and ch == "$":
                out.append("%24")
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def normalize_pattern(value: str) -> str:
    """Canonical form of an ``allow`` / ``disallow`` value.

    Only a ``$`` at the very end is an anchor; any other ``$`` is an ordinary
    character and is encoded as ``%24`` so it matches the encoded URI.
    """
    out = normalize(value, is_pattern=True)
    if "$" in out[:-1]:
        out = out[:-1].replace("$", "%24") + out[-1]
    return out


def normalize_path(value: str) -> str:
    """Canonical form of a URI path (with query), wildcards encoded."""
    return normalize(value, is_pattern=False)


def split_path_query(url: str) -> tuple[str, str | None]:
    """Split ``url`` (absolute, scheme-relative or a bare path) into path and query.

    The query is ``None`` when there is no ``?`` at all and ``""`` for a bare
    ``?``. The fragment is dropped.
    """
    no_fragment = url.strip().split("#", 1)[0]
    if _SCHEME.match(no_fragment) or no_fragment.startswith("//"):
        rest = no_fragment.split("//", 1)[1]
        cut = min((i for i in (rest.find("/"), rest.find("?")) if i >= 0), default=len(rest))
        no_fragment = rest[cut:]
    path, sep, query = no_fragment.partition("?")
    return path, (query if sep else None)


def request_path(url: str) -> str:
    """The part of ``url`` that robots.txt rules are matched against.

    That is the path plus the query string, without the fragment, normalised.
    A bare path (``/a?b``) is accepted as well as an absolute URL. An empty
    path becomes ``/``.
    """
    path, query = split_path_query(url)
    if not path.startswith("/"):
        path = "/" + path
    if query is not None:
        path = f"{path}?{query}"
    return normalize_path(path)
