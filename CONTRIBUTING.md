# Contributing

Thanks for taking the time to improve robots-txt-lab. Bug reports, new lint
checks, matching fixes and documentation corrections are all welcome.

## Reporting a bug

Open an issue with:

- the command you ran and the full output (`--format json` helps)
- your Python version (`python --version`) and operating system
- the smallest robots.txt that reproduces the problem, and the URL and user
  agent you tested
- for matching disagreements: what you expected and where that behaviour is
  documented (RFC 9309 section, Google documentation page, or a Search Console
  robots.txt report)

Replace private host names with `example.com`.

## Development setup

You need Python 3.9 or newer.

```console
$ git clone https://github.com/saizul/robots-txt-lab.git
$ cd robots-txt-lab
$ python -m venv .venv
$ . .venv/bin/activate
$ python -m pip install -e ".[dev]"
```

Before every commit:

```console
$ ruff check .
$ ruff format --check .
$ pytest
```

All three must pass; CI runs them on Python 3.9 to 3.13.

## Guidelines

- **No runtime dependencies.** Standard library only. Development tools go in
  the `dev` extra.
- **Tests never touch the network.** Use the `FakeTransport` in
  `tests/conftest.py` for anything that fetches.
- **Cite the source of a behaviour.** A change to matching or parsing needs a
  test and a reference to RFC 9309 or Google's documentation. Behaviour that
  only one crawler has goes behind the `google` profile, not into the
  default path of `rfc`.
- **Every change comes with a test** that fails without it.
- Support every Python version in the CI matrix: no syntax or library features
  newer than 3.9 (use `from __future__ import annotations` for modern type
  hints).
- Add a line to the `Unreleased` section of `CHANGELOG.md` for anything a user
  would notice.

## Project layout

```text
src/robots_txt_lab/
    encoding.py    percent-encoding normalisation, request path extraction
    agents.py      product tokens, crawler fallbacks
    models.py      Rule, Group, Directive, RobotsTxt
    parser.py      the parser
    matcher.py     wildcard matching and rule precedence
    robots.py      Robots and Verdict: group selection and decisions
    scope.py       which robots.txt governs a URL
    fetch.py       HTTP fetch and status handling
    sitemaps.py    sitemap checks
    lint.py        the linter
    diff.py        rule and verdict diff
    output.py      text and JSON renderers
    cli.py         command-line interface
tests/             pytest suite
examples/          sample files, library script, CI workflow
```

## Adding a lint check

Add the check to `lint()` in `src/robots_txt_lab/lint.py` with a short,
stable kebab-case code, a severity (`error` only for things that certainly
break crawling) and a hint that says how to fix it. Add tests for a file that
triggers it and one that does not, add it to the `CHECKS` catalog in the same
module (the SARIF output and `--list-checks` read it) and list it in the README
table; a test fails when a code is missing from either.

## Pull requests

Keep pull requests focused on one change, describe what it does and why, and
mention anything you could not test. By contributing you agree that your work
is released under the MIT license of this project.

## Code of conduct

This project follows a [code of conduct](CODE_OF_CONDUCT.md). By taking part you
agree to uphold it.
