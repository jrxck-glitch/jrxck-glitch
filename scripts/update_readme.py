"""
Updates README.md with:
  - your latest commits across your public repos
  - what you're currently learning (from learning.json)
  - an AI-written hot take on today's top tech news
  - a "last updated" timestamp

Runs in GitHub Actions. Uses only the Python standard library.
"""

import json
import os
import re
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

USER = os.environ.get("GITHUB_REPOSITORY_OWNER", "your-username")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MODEL = os.environ.get("AI_MODEL", "openai/gpt-4.1-mini")
README = "README.md"


class KeepPostRedirect(urllib.request.HTTPRedirectHandler):
    """Python's default turns a redirected POST into a GET and drops the body. Keep it a POST."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        print(f"Redirected ({code}) to {newurl}")
        return urllib.request.Request(
            newurl, data=req.data, headers=dict(req.header_items()), method=req.get_method()
        )


def get_json(url, headers=None, data=None):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def gh_headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": USER}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def recent_commits(limit=5):
    """Latest commit from each of your most recently pushed repos."""
    repos = get_json(
        f"https://api.github.com/users/{USER}/repos?sort=pushed&per_page=10&type=owner",
        gh_headers(),
    )
    lines = []
    for repo in repos:
        if repo["fork"] or repo["name"] == USER:
            continue  # skip forks and this profile repo itself
        try:
            commits = get_json(
                f"https://api.github.com/repos/{USER}/{repo['name']}/commits?per_page=1",
                gh_headers(),
            )
        except Exception:
            continue
        if not commits:
            continue
        c = commits[0]
        msg = c["commit"]["message"].splitlines()[0][:70]
        date = c["commit"]["author"]["date"][:10]
        lines.append(f"- **[{repo['name']}]({repo['html_url']})**: {msg} `{date}`")
        if len(lines) >= limit:
            break
    return "\n".join(lines) or "- Nothing public yet. Stay tuned."


def learning():
    with open("learning.json") as f:
        items = json.load(f)
    return "\n".join(f"- {item}" for item in items)


def top_tech_news(n=5):
    ids = get_json("https://hacker-news.firebaseio.com/v0/topstories.json")[:n]
    stories = []
    for i in ids:
        s = get_json(f"https://hacker-news.firebaseio.com/v0/item/{i}.json")
        stories.append({"title": s.get("title", ""), "url": s.get("url", f"https://news.ycombinator.com/item?id={i}")})
    return stories


def hot_take():
    stories = top_tech_news()
    headlines = "\n".join(f"{i+1}. {s['title']}" for i, s in enumerate(stories))
    prompt = (
        "You write a daily 'hot take' for a CS student's GitHub profile. "
        "Pick the most interesting headline below and give a bold, funny, but not mean "
        "opinion on it in 2 sentences max. No hashtags, no emojis, no em dashes. "
        "Reply as JSON: {\"pick\": <headline number>, \"take\": \"...\"}\n\n" + headlines
    )
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
    }).encode()
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = "https://models.github.ai/inference/chat/completions"
    opener = urllib.request.build_opener(KeepPostRedirect)
    req = urllib.request.Request(url, headers=headers, data=body, method="POST")
    with opener.open(req, timeout=60) as r:
        raw = r.read().decode()
        print(f"AI status {r.status} from {r.geturl()}")
    print("AI raw response:", raw[:500])
    text = json.loads(raw)["choices"][0]["message"]["content"].strip()

    # Models don't always return clean JSON, so dig it out, or fall back to plain text.
    pick, take = 1, text
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            result = json.loads(match.group(0))
            pick, take = int(result.get("pick", 1)), result.get("take", text)
        except (json.JSONDecodeError, ValueError):
            pass
    take = take.replace("—", ",").strip().strip('"')
    if not take:
        raise ValueError("empty take")
    story = stories[min(max(pick, 1), len(stories)) - 1]
    return f"> {take}\n>\n> *Re: [{story['title']}]({story['url']})*"


def replace_section(content, name, new_text):
    pattern = rf"(<!-- {name}:START -->).*?(<!-- {name}:END -->)"
    return re.sub(pattern, lambda m: f"{m.group(1)}\n{new_text}\n{m.group(2)}", content, flags=re.S)


def main():
    with open(README) as f:
        content = f.read()

    # Each section is independent: if one fails, the old version stays.
    for name, fn in [("COMMITS", recent_commits), ("LEARNING", learning), ("HOTTAKE", hot_take)]:
        try:
            content = replace_section(content, name, fn())
        except Exception as e:
            print(f"Skipping {name}: {e}")

    now = datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d, %Y at %I:%M %p CT")
    content = replace_section(content, "UPDATED", f"<sub>Auto-updated {now} by a GitHub Action</sub>")

    with open(README, "w") as f:
        f.write(content)


if __name__ == "__main__":
    main()
