# Security policy

## Supported versions

Security fixes are made for the latest released minor version.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | yes       |

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's
[private vulnerability reporting](https://github.com/saizul/robots-txt-lab/security/advisories/new)
for this repository and include a description, the input that triggers the
problem and the version you used.

You can expect an acknowledgement within a few days. Once a fix is released
the advisory is published with credit to the reporter, unless you prefer to
stay anonymous.

## Scope

robots-txt-lab parses untrusted input and, with `fetch` or a URL argument,
makes HTTP requests. Things that count as vulnerabilities include:

- input that makes parsing or matching take excessive time or memory (the
  parser reads at most 500 KiB, and the matcher is designed not to backtrack)
- reading more than the size limit from a server
- following redirects beyond the configured limit
- writing files other than the one named with `--save`

Note that `fetch` requests whatever URL you give it, including private network
addresses. Do not expose the command to untrusted users as a service without
your own URL filtering.
