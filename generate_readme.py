#!/usr/bin/env python3
"""
Dynamic GitHub Profile README Generator

Features:
- Zero hardcoded usernames
- Automatically detects repository owner
- Uses live GitHub REST API
- Generates README.md dynamically
- Works with GitHub Actions
"""

import os
import requests
from datetime import datetime, timezone
from urllib.parse import quote

GITHUB_API = "https://api.github.com"

# ------------------------------------------------------------------
# Detect GitHub username dynamically
# ------------------------------------------------------------------

repository = os.getenv("GITHUB_REPOSITORY", "")

if "/" not in repository:
    raise RuntimeError(
        "GITHUB_REPOSITORY environment variable is missing."
    )

USERNAME = repository.split("/")[0]

TOKEN = os.getenv("GITHUB_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "GITHUB_TOKEN environment variable not found."
    )

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
}


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def github_get(endpoint: str):
    response = requests.get(
        f"{GITHUB_API}{endpoint}",
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


# ------------------------------------------------------------------
# User Profile
# ------------------------------------------------------------------

print("Fetching profile...")

user = github_get(f"/users/{USERNAME}")

name = user.get("name") or USERNAME
bio = user.get("bio") or "GitHub Developer"
location = user.get("location") or "Unknown"

blog = user.get("blog") or ""

if blog and not blog.startswith("http"):
    blog = "https://" + blog

avatar = user.get("avatar_url")

followers = user.get("followers", 0)
following = user.get("following", 0)

public_repos = user.get("public_repos", 0)

created = user.get("created_at", "")[:10]

# ------------------------------------------------------------------
# Repositories
# ------------------------------------------------------------------

print("Fetching repositories...")

repos = github_get(
    f"/users/{USERNAME}/repos?per_page=100&type=owner&sort=updated"
)

repos = [r for r in repos if not r["fork"]]

total_stars = sum(r["stargazers_count"] for r in repos)
total_forks = sum(r["forks_count"] for r in repos)

top_repos = sorted(
    repos,
    key=lambda r: r["stargazers_count"],
    reverse=True
)[:6]

# ------------------------------------------------------------------
# Languages
# ------------------------------------------------------------------

language_count = {}

for repo in repos:

    lang = repo.get("language")

    if not lang:
        continue

    language_count[lang] = language_count.get(lang, 0) + 1

top_languages = sorted(
    language_count.items(),
    key=lambda x: x[1],
    reverse=True
)

# ------------------------------------------------------------------
# README
# ------------------------------------------------------------------

generated = datetime.now(
    timezone.utc
).strftime("%Y-%m-%d %H:%M UTC")

subtitle = quote(bio)

markdown = f"""
<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&height=220&text={quote(name)}&desc={subtitle}&fontSize=48"/>

# {name}

{bio}

</div>

---

## 👤 Profile

- **Username:** `{USERNAME}`
- **Location:** {location}
- **Followers:** {followers}
- **Following:** {following}
- **Public Repositories:** {public_repos}
- **GitHub Member Since:** {created}

{"- **Portfolio:** " + blog if blog else ""}

---

## 📊 GitHub Stats

<p align="center">

<img height="170" src="https://github-readme-stats.vercel.app/api?username={USERNAME}&show_icons=true&theme=github_dark"/>

<img height="170" src="https://github-readme-stats.vercel.app/api/top-langs/?username={USERNAME}&layout=compact&theme=github_dark"/>

</p>

---

## 🔥 GitHub Streak

<p align="center">

<img src="https://streak-stats.demolab.com?user={USERNAME}&theme=dark"/>

</p>

---

## 📈 Contribution Graph

<p align="center">

<img src="https://github-readme-activity-graph.vercel.app/graph?username={USERNAME}&theme=github-dark"/>

</p>

---

## 🚀 Top Repositories

"""

for repo in top_repos:

    markdown += f"""
### [{repo['name']}]({repo['html_url']})

{repo.get('description') or 'No description provided.'}

⭐ Stars: {repo['stargazers_count']}

🍴 Forks: {repo['forks_count']}

Language: `{repo.get('language') or 'Unknown'}`
"""

markdown += "\n---\n"

markdown += "## 🛠️ Top Languages\n\n"

for lang, count in top_languages:

    markdown += f"- {lang} ({count} repositories)\n"

markdown += f"""

---

## 📊 Summary

| Metric | Value |
|----------|------:|
| Public Repositories | {public_repos} |
| Total Stars | {total_stars} |
| Total Forks | {total_forks} |
| Followers | {followers} |
| Following | {following} |

---

## 🐍 Contribution Snake

<picture>

<source
media="(prefers-color-scheme: dark)"
srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">

<img
src="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake.svg">

</picture>

---

<div align="center">

Generated automatically on **{generated}**

</div>
"""

with open(
    "README.md",
    "w",
    encoding="utf-8",
) as f:
    f.write(markdown)

print("README.md generated successfully.")

