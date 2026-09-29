"""Refresh the auto-generated sections of the profile README.

Fills the blocks between <!--ACTIVITY:START--> / <!--ACTIVITY:END--> and
<!--REPOS:START--> / <!--REPOS:END--> from the public GitHub API.
Usage: python scripts/update_readme.py README.v2.md  (GITHUB_TOKEN optional)
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

USER = os.environ.get("GH_USER", "Bentil4")
SKIP_REPOS = {f"{USER}/{USER}"}
LIMIT = 5


def api(path):
    req = urllib.request.Request(f"https://api.github.com{path}", headers={"Accept": "application/vnd.github+json"})
    if token := os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res)


_public = {}


def is_public(repo):
    """Events outlive a repo going private; hide those so visitors never hit a 404."""
    if repo not in _public:
        try:
            _public[repo] = not api(f"/repos/{repo}")["private"]
        except urllib.error.HTTPError:
            _public[repo] = False
    return _public[repo]


def ago(iso):
    days = (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"


def link(repo):
    return f"[{repo.split('/')[1]}](https://github.com/{repo})"


def describe(e):
    repo, p, kind = e["repo"]["name"], e.get("payload", {}), e["type"]
    if repo in SKIP_REPOS or not is_public(repo):
        return None
    if kind == "PushEvent":
        n = p.get("size") or len(p.get("commits", [])) or 1
        return f"⬆️ Pushed {n} commit{'s' if n != 1 else ''} to {link(repo)}"
    if kind == "PullRequestEvent" and p.get("action") in ("opened", "closed"):
        pr = p["pull_request"]
        verb = "🔀 Merged" if pr.get("merged") else "🚀 Opened" if p["action"] == "opened" else None
        return verb and f"{verb} PR [#{pr['number']}](https://github.com/{repo}/pull/{pr['number']}) in {link(repo)}"
    if kind == "IssuesEvent" and p.get("action") == "opened":
        n = p["issue"]["number"]
        return f"🐛 Opened issue [#{n}](https://github.com/{repo}/issues/{n}) in {link(repo)}"
    if kind == "CreateEvent" and p.get("ref_type") == "repository":
        return f"✨ Created a new repo, {link(repo)}"
    if kind == "ReleaseEvent":
        return f"🏷️ Released {p['release']['tag_name']} of {link(repo)}"
    return None


def activity():
    lines, seen = [], set()
    for e in api(f"/users/{USER}/events/public?per_page=100"):
        text = describe(e)
        if text and text not in seen:  # collapse repeated pushes to the same repo
            seen.add(text)
            lines.append(f"{len(lines) + 1}. {text} · <sub>{ago(e['created_at'])}</sub>")
        if len(lines) == LIMIT:
            break
    return "\n".join(lines) or "_No public activity in the last 90 days._"


def repos():
    rows = ["| Repo | What it is | Language | Updated |", "| --- | --- | --- | --- |"]
    picked = [r for r in api(f"/users/{USER}/repos?sort=pushed&per_page=20")
              if not r["fork"] and not r["archived"] and r["full_name"] not in SKIP_REPOS][:LIMIT]
    for r in picked:
        desc = " ".join((r["description"] or "-").split()).replace("|", "\\|")
        desc = desc if len(desc) <= 90 else desc[:87].rstrip() + "…"
        rows.append(f"| [{r['name']}]({r['html_url']}) | {desc} | {r['language'] or '-'} | {ago(r['pushed_at'])} |")
    return "\n".join(rows)


def fill(text, name, body):
    pattern = re.compile(rf"(<!--{name}:START-->).*?(<!--{name}:END-->)", re.S)
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", text)


if __name__ == "__main__":
    for path in sys.argv[1:] or ["README.md"]:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        text = fill(fill(text, "ACTIVITY", activity()), "REPOS", repos())
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
