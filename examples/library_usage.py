"""Use robots-txt-lab as a library.

python examples/library_usage.py
"""

from pathlib import Path

from robots_txt_lab import Robots, diff, lint

here = Path(__file__).parent
robots = Robots.from_text((here / "robots.txt").read_bytes())

# Single verdict, with the deciding rule.
v = robots.check("https://shop.example.com/search?q=widget", "Bingbot")
print(f"{v.user_agent}: {'allowed' if v.allowed else 'blocked'} by {v.rule} (line {v.rule.line})")

# A full HTTP user agent string works too; the product token is picked out of it.
ua = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
print("Googlebot may fetch /search:", robots.allowed("https://shop.example.com/search?q=widget", ua))

# Lint
for issue in lint(robots.parsed, robots_url="https://shop.example.com/robots.txt"):
    print(f"line {issue.line}: {issue.severity}: {issue.message}")

# Diff against the proposed version
new = Robots.from_text((here / "robots.new.txt").read_bytes())
urls = [u for u in (here / "urls.txt").read_text().splitlines() if u and not u.startswith("#")]
result = diff(robots, new, urls, ["Googlebot", "Bingbot"])
for change in result.verdict_changes:
    print(f"{change.user_agent} {change.url}: {change.direction}")

# Fetching (network): status codes are handled per RFC 9309 / Google
# from robots_txt_lab import fetch
# result = fetch("https://www.example.com/")
# print(result.outcome, result.robots.allowed("https://www.example.com/x", "Googlebot"))
