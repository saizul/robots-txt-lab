# robots-txt-lab

[![CI](https://github.com/saizul/robots-txt-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/saizul/robots-txt-lab/actions/workflows/ci.yml)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![dependencies](https://img.shields.io/badge/runtime%20dependencies-0-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Parse, test, lint and diff robots.txt files the way [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) and
[Google](https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec) read them.

A one-character change in robots.txt can take a whole site out of search, and most checkers on the web disagree with
Googlebot in the corner cases: which group applies, which of two matching rules wins, what `$` means in the middle of a
path, what happens when the file returns 503. `robots-txt-lab` implements the standard and Google's documented
behaviour, tells you which rule on which line decided each verdict, and shows which URLs change verdict between two
versions of a file before you deploy it.

```console
$ robots-txt-lab test examples/robots.txt https://shop.example.com/search?q=widget --ua Googlebot --ua Bingbot
ALLOWED    Googlebot        https://shop.example.com/search?q=widget  <- no rule matches [group googlebot]
DISALLOWED Bingbot          https://shop.example.com/search?q=widget  <- disallow: /search (line 8) [group *]

2 check(s): 1 allowed, 1 disallowed
```

It is a command-line tool and a Python library with **no runtime dependencies** (standard library only), for Python
3.9 and newer.

## Features

- **RFC 9309 matching**
  - group selection by product token, case-insensitive, with groups for the same token merged and the `*` group as
    fallback (specific and `*` groups are never combined)
  - longest match wins, measured in octets of the rule path; `allow` wins ties
  - `*` matches any sequence of characters, `$` anchors only at the end of a pattern
  - percent-encoding normalisation of rules and URLs: non-ASCII is encoded, hex is upper-cased, escapes of unreserved
    characters are decoded (`/%62%61%7A` equals `/baz`), escapes of reserved characters are kept
  - `/robots.txt` is always allowed; rules outside a group and rules without a path are ignored
- **Google's documented behaviour** (`--profile google`, the default)
  - `googlebot/1.2` and `googlebot*` on a user-agent line mean `googlebot`
  - crawler fallbacks: Googlebot-Image, Googlebot-Video, Googlebot-News and Google-InspectionTool follow a `Googlebot`
    group when they have none of their own; GoogleOther-Image and GoogleOther-Video fall back to `GoogleOther`
  - AdsBot-Google, AdsBot-Google-Mobile, Mediapartners-Google and APIs-Google ignore the `*` group
  - the misspellings and missing colons Google's parser accepts (`dissallow`, `useragent`, `site-map`, `disallow /x`)
  - the UTF-8 byte order mark is ignored and content after 500 KiB is ignored
  - fetch status handling: 2xx parsed, 3xx followed up to five hops, 4xx (except 429) means no restrictions, 5xx,
    429 and network errors mean complete disallow
- **Strict mode** (`--profile rfc`): only what RFC 9309 defines, no crawler-specific rules, no typo tolerance, 429
  handled as any other 4xx.
- **Verdicts with reasons**: the deciding rule and its line, the group used, the normalised path, and why (no group,
  no matching rule, unavailable, unreachable).
- **Linter** with 41 checks, including unknown directives, `crawl-delay` (ignored by Google), `noindex`, rules outside
  a group, blocking the whole site, blocking CSS and JavaScript, sitemap URL problems, BOM, size limit, non-UTF-8
  content, HTML served as robots.txt, field name case, case-sensitive paths, conflicting and duplicate rules.
- **Inline suppressions**: accept a lint issue on purpose with a `# robots-txt-lab: disable=CODE` comment right where
  it happens; crawlers ignore comments, so the file behaves exactly the same.
- **CI-friendly lint output**: SARIF 2.1.0 for GitHub code scanning and other SARIF viewers, and GitHub Actions
  annotations that show up on the changed lines of a pull request.
- **Diff** two versions: added and removed rules per group, sitemap changes, and every test URL and user agent whose
  verdict flips. Without a URL list, probe URLs are derived from the rules of both files.
- **Fetch** a live robots.txt with redirect, status and size handling, then test, lint or save it.
- **Sitemap extraction** and validation.
- **Text and JSON output** for every command, and exit codes for CI.

## Installation

The project is not on PyPI yet. Install it from GitHub or from a checkout:

```console
$ pip install "git+https://github.com/saizul/robots-txt-lab@v0.1.0"
```

```console
$ git clone https://github.com/saizul/robots-txt-lab.git
$ cd robots-txt-lab
$ python -m pip install .
```

This installs the `robots-txt-lab` command. `python -m robots_txt_lab` works too.

## Docker image

A multi-arch image (linux/amd64, linux/arm64) is published to GitHub Packages:

```bash
docker pull ghcr.io/saizul/robots-txt-lab:latest
docker run --rm ghcr.io/saizul/robots-txt-lab:latest fetch https://www.example.com/
docker run --rm -v "$PWD:/work" ghcr.io/saizul/robots-txt-lab:latest lint robots.txt
```

Mount the folder with your files at `/work`, the working directory of the image. Release images are also tagged with
the version (`ghcr.io/saizul/robots-txt-lab:0.1.0`) and every build with its commit SHA.

## Usage

Every command takes a robots.txt **file**, `-` for **standard input**, or an **http(s) URL**. For a URL the
robots.txt of that site is fetched and the HTTP outcome is applied: a 404 means "allow everything", a 503 means
"disallow everything".

### test

```console
$ robots-txt-lab test robots.txt /checkout/ https://shop.example.com/product/1 --ua Googlebot
$ robots-txt-lab test https://www.example.com/ /private/ --ua "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"
$ robots-txt-lab test robots.txt --urls-file urls.txt --ua Googlebot --ua Bingbot --format json
$ robots-txt-lab test robots.txt /admin/ --expect disallowed     # exit 1 if any URL is allowed
$ robots-txt-lab test robots.txt --cases cases.txt               # exit 1 on any failed expectation
```

`--ua` takes a product token (`Googlebot`, `Bingbot`, `*`) or a full HTTP user agent string; the default is
`Googlebot`. A cases file holds one expectation per line, see [`examples/cases.txt`](examples/cases.txt):

```text
# <allow|disallow> <url> [user agent]
allow    https://shop.example.com/product/blue-widget
disallow https://shop.example.com/checkout/step-1
disallow https://shop.example.com/search?q=widget   Bingbot
```

### lint

```console
$ robots-txt-lab lint examples/problems.robots.txt
examples/problems.robots.txt:1: error: rule before any user-agent line is ignored: 'Disallow: /tmp/' [rule-outside-group]
    hint: Add a 'User-agent: *' line above it.
examples/problems.robots.txt:13: error: disallow: / blocks the entire site for Googlebot [blocks-entire-site]
    hint: Intended for a staging site? Remove it before launch.
examples/problems.robots.txt:15: error: sitemap URLs must be absolute, including the protocol and host: '/sitemap.xml' [sitemap-not-absolute]
examples/problems.robots.txt:3: warning: disallow: /wp-includes/ blocks CSS or JavaScript for crawlers that use the '*' group (e.g. /wp-includes/site.css) [blocks-resources]
...
examples/problems.robots.txt:7: warning: crawl-delay is ignored by Google (Bing and Yandex read it) [crawl-delay-ignored]
    hint: Googlebot adjusts its crawl rate automatically; to slow it down temporarily, return 503 or 429.
...
3 error(s), 7 warning(s), 2 info
```

| Option                  | Meaning                                                                  |
| ----------------------- | ------------------------------------------------------------------------ |
| `--fail-on SEVERITY`    | exit 1 when an issue of `error` (default), `warning` or `info` or worse is found; `never` to always exit 0 |
| `--ignore CODES`        | comma-separated issue codes to skip, repeatable                         |
| `--robots-url URL`      | where the file is served, for the sitemap host checks (automatic for URLs) |
| `--format FORMAT`       | `text` (default), `json`, `sarif` or `github`, see [CI output](#ci-output) |
| `--no-inline-ignores`   | report issues even when an inline comment suppresses them               |
| `--list-checks`         | print every check code with its default severity and a description, then exit |

#### Inline suppressions

Some findings are intentional: a staging host that really should block everything, a `Crawl-delay` kept for Bing.
Instead of turning a check off for every file with `--ignore`, mark the line in robots.txt itself:

```text
# robots-txt-lab: disable-file=bom
User-agent: *
Disallow: /wp-includes/   # robots-txt-lab: disable=blocks-resources

User-agent: bingbot
# robots-txt-lab: disable-next-line=crawl-delay-ignored
Crawl-delay: 5
```

| Comment                                   | Silences                                                                 |
| ----------------------------------------- | ------------------------------------------------------------------------ |
| `# robots-txt-lab: disable=CODES`         | the listed codes on the same line                                        |
| `# robots-txt-lab: disable-next-line=CODES` | the listed codes on the next line that is not blank or a comment       |
| `# robots-txt-lab: disable-file=CODES`    | the listed codes anywhere in the file, including issues without a line (`size-near-limit`) |

`CODES` is a comma-separated list of check codes (see `robots-txt-lab lint --list-checks`), or `all`. The marker is
case-insensitive and `=` may be replaced by a space. Suppressed issues do not count for `--fail-on`; the text summary
shows how many were suppressed, JSON lists them under `suppressed`, and SARIF reports them with an `inSource`
suppression so code scanning shows them as dismissed. A comment that silences nothing is reported as
`unused-suppression` (info), and one that cannot be read or names an unknown code as `invalid-suppression` (warning);
those two are never suppressed by comments. `--no-inline-ignores` reports everything, for an audit.

#### CI output

```console
$ robots-txt-lab lint public/robots.txt --format github
::error file=public/robots.txt,line=13,title=robots-txt-lab blocks-entire-site::disallow: / blocks the entire site for Googlebot (hint: Intended for a staging site? Remove it before launch.)
$ robots-txt-lab lint public/robots.txt --format sarif > robots-txt.sarif
```

`--format github` prints [workflow commands](https://docs.github.com/actions/reference/workflow-commands-for-github-actions)
(`::error`, `::warning`, `::notice` for info), so issues appear as annotations on the pull request. `--format sarif`
writes a [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html) log with one rule per check
code; upload it with `github/codeql-action/upload-sarif` as in
[`examples/github-code-scanning.yml`](examples/github-code-scanning.yml). File paths are written relative, as given on
the command line, so run the command from the repository root. The exit code follows `--fail-on` in every format.

### diff

```console
$ robots-txt-lab diff examples/robots.txt examples/robots.new.txt --urls-file examples/urls.txt
Rule changes:
  + [*] disallow: /*?filter=  (line 10)
  + [googlebot] disallow: /*?filter=  (line 16)
  - sitemap: https://shop.example.com/sitemap-products.xml

Verdict changes (11 URL(s) given x 3 agent(s)):
  Googlebot    https://shop.example.com/category/shoes?filter=red  allowed -> DISALLOWED  <- disallow: /*?filter= (line 16)
  Bingbot      https://shop.example.com/category/shoes?filter=red  allowed -> DISALLOWED  <- disallow: /*?filter= (line 10)
  *            https://shop.example.com/category/shoes?filter=red  allowed -> DISALLOWED  <- disallow: /*?filter= (line 10)
```

Rules are compared after normalisation, so reordering lines, changing case of field names, adding comments or
switching between `ツ` and `%E3%83%84` is not reported as a change. The default agents are `Googlebot`, `Bingbot` and
`*` (any crawler without its own group); pass `--ua` to choose. Without `-u`/`--urls-file`, test URLs are derived
from the rules of both files. `--fail-on-change` exits 1 when any verdict changes.

Either side can be a URL, so `robots-txt-lab diff https://www.example.com/ new-robots.txt` compares production with a
candidate file.

### fetch

```console
$ robots-txt-lab fetch http://github.com/
robots.txt: http://github.com/robots.txt
  301  http://github.com/robots.txt
  200  https://github.com/robots.txt
Outcome: ok (HTTP 200), parsed; its rules apply
...
$ robots-txt-lab fetch https://www.example.com/ --lint --save robots.fetched.txt --format json
```

Any URL on the site works; the robots.txt location is derived from its scheme, host and port. `--request-ua` sets the
`User-Agent` header and `--timeout` the timeout in seconds. The exit code is 0 when the file was fetched and parsed, 1
when it was unavailable or unreachable.

### sitemaps

```console
$ robots-txt-lab sitemaps https://www.example.com/
https://www.example.com/sitemap_index.xml
```

### Exit codes

| Code | Meaning                                                                         |
| ---- | ------------------------------------------------------------------------------- |
| 0    | success                                                                         |
| 1    | `test` expectation failed, `lint` found issues at `--fail-on`, `diff --fail-on-change` saw a change, `fetch` did not get a parsable file |
| 2    | usage error, unreadable file                                                     |

## How it decides

1. **Fetch outcome.** For a URL source the HTTP result is applied first:

   | Result                 | `google` profile                 | `rfc` profile                       |
   | ---------------------- | -------------------------------- | ----------------------------------- |
   | 2xx                    | parse the body                   | parse the body                      |
   | 3xx                    | follow up to 5 redirects, even to other hosts; more than 5 is treated like 404 | same |
   | 429                    | complete disallow (server error) | no restrictions (4xx)               |
   | other 4xx              | no restrictions                  | no restrictions                     |
   | 5xx, network errors    | complete disallow                | complete disallow                   |

   Google stops crawling for 12 hours after a 5xx and then uses its last cached copy for up to 30 days. This tool
   keeps no cache, so it reports the complete disallow.

2. **Parsing.** The BOM is skipped and only the first 500 KiB are read. Lines split on CR, LF or CRLF, `#` starts a
   comment, field names are case-insensitive. A group is a run of `user-agent` lines followed by rules; a
   `user-agent` line after a rule starts the next group. `sitemap` and unknown lines never end a group.

3. **Group.** The crawler's product token is matched case-insensitively against every group's tokens. All groups for
   that token are merged. In the `google` profile the token's fallbacks are tried next. If nothing matches, the `*`
   groups apply, except for the AdsBot family. If there is no `*` group either, everything is allowed.

4. **Rule.** The path and query of the URL (no fragment) and every rule are normalised, then every rule is matched
   from the first character. The longest matching rule wins; on equal length `allow` wins. No match means allowed.

The matcher tracks the set of reachable positions instead of translating patterns to regular expressions, so a
pattern such as `/*a*a*a*a*b` costs `O(path x pattern)` and cannot backtrack exponentially.

## Library use

```python
from robots_txt_lab import Robots, diff, fetch, lint

robots = Robots.from_text(open("robots.txt", "rb").read())        # or profile="rfc"

verdict = robots.check("https://example.com/search?q=x", "Bingbot")
verdict.allowed          # False
verdict.rule             # Rule(allow=False, path='/search', pattern='/search', line=8)
verdict.group_token      # '*'
verdict.reason           # 'matched-disallow'

robots.allowed("/public/page", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
robots.sitemaps          # ['https://example.com/sitemap.xml']

for issue in lint(robots.parsed, robots_url="https://example.com/robots.txt"):
    print(issue.line, issue.severity, issue.code, issue.message)

result = fetch("https://www.example.com/")          # status codes, redirects, size limit
result.outcome, result.robots.allowed("https://www.example.com/x", "Googlebot")

changes = diff(robots, Robots.from_text(new_text), ["/a", "/b?c=1"], ["Googlebot"]).verdict_changes
```

`fetch` accepts a `transport` callable, so tests (and proxies) can supply responses without the network; see
`tests/conftest.py`. More in [`examples/library_usage.py`](examples/library_usage.py).

## Lint checks

| Code                     | Severity   | What it finds                                                                 |
| ------------------------ | ---------- | ----------------------------------------------------------------------------- |
| `rule-outside-group`     | error      | `allow`/`disallow` before the first `user-agent` line (ignored)                |
| `blocks-entire-site`     | error/warning/info | `Disallow: /` for `*` or Googlebot (error), for other agents (warning), or with allow exceptions (info) |
| `absolute-url-rule`      | error      | a rule written as a full URL                                                  |
| `html-content`           | error      | the file looks like an HTML page                                              |
| `size-limit`             | error      | larger than 500 KiB; the rest is ignored                                      |
| `sitemap-not-absolute`, `sitemap-bad-scheme`, `sitemap-invalid-url`, `sitemap-empty` | error | unusable sitemap lines |
| `invalid-suppression`    | warning    | a `# robots-txt-lab:` comment that cannot be read or names an unknown check   |
| `blocks-resources`       | warning    | rules that block CSS or JavaScript for Googlebot or the `*` group             |
| `crawl-delay-ignored`    | warning    | `crawl-delay`, which Google ignores                                           |
| `noindex-unsupported`    | warning    | `noindex` in robots.txt, unsupported by Google since September 2019           |
| `unknown-directive`, `nonstandard-directive` | warning/info | fields no major crawler understands, or non-standard ones |
| `misspelled-directive`, `missing-colon` | warning | lines Google accepts but other crawlers may not                         |
| `invalid-line`, `invalid-user-agent` | warning | lines that are not `field: value`, user-agent values without a token     |
| `path-no-leading-slash`  | warning    | a rule that does not start with `/` or `*` and so never matches               |
| `dollar-not-at-end`      | warning    | `$` in the middle of a pattern, which is literal                              |
| `conflicting-rules`      | warning    | allow and disallow for the same path                                          |
| `redundant-allow`        | info       | an allow rule with no disallow it could override (typo or stale rule?)        |
| `not-utf8`, `size-near-limit`, `sitemap-hash`, `sitemap-scheme-mismatch` | warning | encoding, size and sitemap URL problems |
| `bom`, `directive-case`, `path-case`, `user-agent-token`, `empty-group`, `empty-rule`, `duplicate-rule`, `redundant-wildcard`, `robots-txt-disallowed`, `host-directive`, `clean-param-directive`, `sitemap-duplicate`, `sitemap-cross-host`, `no-groups`, `unused-suppression` | info | worth knowing, rarely wrong |

## Examples

[`examples/`](examples/) has a realistic shop robots.txt, a proposed change to it, a URL list, an expectations file,
a file full of problems for the linter, a library script,
[`github-actions-robots-check.yml`](examples/github-actions-robots-check.yml): a workflow that lints the robots.txt of
your site on every pull request with inline annotations, checks your expectations, and writes the verdict changes
against the base branch to the job summary, and [`github-code-scanning.yml`](examples/github-code-scanning.yml),
which uploads the lint results to GitHub code scanning as SARIF.

## Testing

```console
$ python -m venv .venv && . .venv/bin/activate
$ pip install -e ".[dev]"
$ ruff check . && ruff format --check .
$ pytest
```

The suite (428 tests) includes every example from RFC 9309 (sections 2.2.1 to 2.2.4 and 5) and from Google's robots.txt
specification page: the user-agent precedence table, rule grouping, the wildcard path table, the rule precedence
table and the robots.txt URL validity table. Tests never touch the network; fetching uses a fake transport. CI runs
lint, the tests on Python 3.10 to 3.13, a CLI smoke test and a Docker build.

## Limitations

- **One implementation of the documented behaviour, not Google's code.** Where the documentation is silent, behaviour
  follows Google's open-source parser as far as it is described in public (typo tolerance, missing colons, `*`
  followed by text). If Search Console's robots.txt report disagrees with this tool, trust Search Console and please
  open an issue.
- **Reserved characters are compared as written.** RFC 9309 figure 4 shows `/foo/bar?baz=https://foo.bar` matched as
  `https%3A%2F%2Ffoo.bar`; like Google's parser, this tool does not encode reserved characters such as `:` and `/`,
  so a rule must use the same form as the URL.
- **Crawler fallbacks are a small built-in table** taken from Google's crawler documentation. Other search engines'
  crawlers are matched by their exact token; Bing, Yandex and others may differ from Google in details.
- **No caching.** Google's 12-hour / 30-day handling of server errors needs a previous copy; a fetch here reports
  the immediate effect (complete disallow).
- **robots.txt only.** Indexing controls such as `noindex` meta tags and `X-Robots-Tag` headers are out of scope.
- **The linter's CSS and JavaScript check is heuristic**: it looks for rules with typical asset paths and confirms
  with a probe URL that they are really blocked.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Saizul Amin
