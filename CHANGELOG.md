# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `redundant-allow` lint check (info): an `Allow` rule that no disallow rule could override has no effect,
  which usually means a typo in the path or a disallow rule that was changed or removed. Groups that name the
  same agent are merged as crawlers do; rules with wildcards are treated conservatively and `Allow: /` is not
  reported.
- Inline suppression comments for the linter: `# robots-txt-lab: disable=CODES`
  (same line), `disable-next-line=CODES` and `disable-file=CODES`, with `all`
  as a wildcard. Suppressed issues no longer count for `--fail-on`; the text
  summary counts them and JSON lists them under `suppressed`.
- Two new checks: `invalid-suppression` (warning) for unreadable comments or
  unknown codes, and `unused-suppression` (info) for comments that silence
  nothing.
- `lint --format sarif`: SARIF 2.1.0 output for GitHub code scanning, with one
  rule per check and suppressed issues marked `inSource`.
- `lint --format github`: GitHub Actions `::error` / `::warning` / `::notice`
  annotations.
- `lint --list-checks` and `lint --no-inline-ignores`.
- `CHECKS` catalog, `lint_report()` / `LintReport` and `parse_suppressions()`
  in the library API.
- `examples/github-code-scanning.yml`; the pull request example now annotates
  lint issues.
- Code of conduct, issue forms and a pull request template.

### Changed

- `--format` choices are now per command: `lint` accepts `text`, `json`,
  `sarif` and `github`; the other commands keep `text` and `json`.

## [0.1.0] - 2026-11-12

First public release.

### Added

- robots.txt parser following RFC 9309: groups, merged groups for the same
  product token, comments, CR / LF / CRLF line endings, UTF-8 BOM, 500 KiB
  size limit, rules outside groups and empty rules ignored, other records
  (such as `sitemap`) never ending a group.
- Matcher with `*` and end-anchor `$` wildcards, longest match by octets,
  `allow` winning ties, implicit allow of `/robots.txt`, and a
  backtracking-free algorithm.
- Percent-encoding normalisation of rule paths and URLs.
- `google` profile with Google's documented behaviour: user-agent token
  extraction, crawler fallback tokens, crawlers that ignore the `*` group,
  accepted misspellings and missing colons, 429 handled as a server error.
- `rfc` profile for strict RFC 9309 behaviour.
- Fetching with up to five redirects, 4xx / 5xx / network error handling and
  an injectable transport.
- Linter with 39 checks, including unknown directives, crawl-delay, noindex,
  blocking the whole site, blocking CSS and JavaScript, sitemap URL problems,
  BOM, size, encoding and case.
- Diff of two versions: rule changes, sitemap changes and URL verdict changes,
  with test URLs derived from the rules when none are given.
- Sitemap extraction and validation, robots.txt scope (scheme, host, port,
  IDN) helpers.
- `robots-txt-lab` CLI with `test`, `lint`, `diff`, `fetch` and `sitemaps`,
  text and JSON output, and CI exit codes.
- Docker image definition and publishing workflow.
- Test suite of 383 tests, including the examples from RFC 9309 and Google's
  robots.txt documentation.

[Unreleased]: https://github.com/saizul/robots-txt-lab/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/saizul/robots-txt-lab/releases/tag/v0.1.0
