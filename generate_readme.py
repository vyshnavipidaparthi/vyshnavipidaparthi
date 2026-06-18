#!/usr/bin/env python3
"""
Fully Automated README.md Generator
Pulls 100% of data from GitHub API - zero hardcoding
"""

import os
import requests
from datetime import datetime, timezone
from urllib.parse import quote

# ── Configuration (only username, rest is API-driven) ──────────────────────────
USERNAME    = "SamppurnaTH"
GITHUB_API  = "https://api.github.com"

# ── GitHub API helpers ────────────────────────────────────────────────────────
def gh(path, token):
    """Make authenticated GitHub API call."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = requests.get(f"{GITHUB_API}{path}", headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️  API Error ({path}): {str(e)[:60]}")
        return {} if "user" in path else []

def get_user_data(token):
    """Fetch user profile - name, bio, location, blog, followers, etc."""
    return gh(f"/users/{USERNAME}", token)

def get_user_stats(token):
    """Fetch user statistics via GraphQL - contributions, streaks, etc."""
    query = """
    {
      user(login: "%s") {
        contributionsCollection {
          contributionCalendar {
            totalContributions
          }
          contributionStreak: contributionsByCollection {
            startedAt
            endedAt
          }
        }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          nodes {
            name
            description
            url
            primaryLanguage {
              name
            }
            stargazerCount
            forkCount
            topics: repositoryTopics(first: 5) {
              nodes {
                topic {
                  name
                }
              }
            }
            isInOrganization
          }
        }
        pullRequests {
          totalCount
        }
        issues {
          totalCount
        }
      }
    }
    """ % USERNAME
    
    try:
        r = requests.post(
            "https://api.github.com/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        return r.json().get("data", {}).get("user", {})
    except Exception as e:
        print(f"⚠️  GraphQL Error: {str(e)[:60]}")
        return {}

def get_all_repos(token):
    """Fetch all user repos (paginated)."""
    repos, page = [], 1
    while page <= 5:
        batch = gh(
            f"/users/{USERNAME}/repos?per_page=100&page={page}&sort=updated&type=owner",
            token
        )
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos

def get_pinned(token):
    """Fetch pinned repos via GraphQL."""
    query = """
    {
      user(login: "%s") {
        pinnedItems(first: 6, types: REPOSITORY) {
          nodes {
            ... on Repository {
              name
              description
              url
            }
          }
        }
      }
    }
    """ % USERNAME
    try:
        r = requests.post(
            "https://api.github.com/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        nodes = r.json().get("data", {}).get("user", {}).get("pinnedItems", {}).get("nodes", [])
        return {n["name"] for n in nodes}
    except Exception as e:
        print(f"⚠️  GraphQL Pinned Error: {str(e)[:60]}")
        return set()

def get_user_contributions(token):
    """Fetch contribution streak data from GitHub API."""
    query = """
    {
      user(login: "%s") {
        contributionsCollection {
          totalContributions
          contributionCalendar {
            totalContributions
          }
        }
      }
    }
    """ % USERNAME
    try:
        r = requests.post(
            "https://api.github.com/graphql",
            json={"query": query},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        data = r.json().get("data", {}).get("user", {}).get("contributionsCollection", {})
        return data.get("totalContributions", 0)
    except Exception as e:
        print(f"⚠️  Contributions Error: {str(e)[:60]}")
        return 0

# ── Repo classification (keyword-based, no hardcoding) ────────────────────────
ML_KW = [
    "cancer", "disease", "health", "predict", "classif", "regress", "neural",
    "iris", "titanic", "stock", "segment", "knn", "lstm", "nlp", "sentiment",
    "model", "train", "diabetes", "fraud", "spam", "mnist", "cnn", "rnn",
]

AIAPP_KW = [
    "vebhav", "meetiq", "shipespace", "farmconnect", "kareerpilot",
    "agent", "assistant", "lms", "flyhii", "gpt", "rag", "chatbot",
]

FS_KW = [
    "portfolio", "website", "frontend", "dashboard", "ui", "app",
    "fullstack", "client", "landing", "blog", "service",
]

def classify(repo):
    """Auto-classify repo from name, description, language."""
    name = repo["name"].lower()
    desc = (repo.get("description") or "").lower()
    lang = (repo.get("language") or "").lower()
    topics = " ".join(repo.get("topics", [])).lower()
    src = f"{name} {desc} {topics}"

    if any(k in src for k in AIAPP_KW):
        return "ai"
    if any(k in src for k in ML_KW):
        return "ml"
    if any(k in src for k in FS_KW) or lang in ("typescript", "javascript"):
        return "fs"
    if lang == "python":
        return "ml"
    return "other"

# ── Markdown builders ─────────────────────────────────────────────────────────
STATS_BASE = "https://github-readme-stats.vercel.app/api"
THEME = "theme=github_dark&hide_border=true&title_color=a78bfa&icon_color=a78bfa&text_color=e2e8f0&bg_color=0d1117"

def pin_card(name):
    url = f"{STATS_BASE}/pin/?username={USERNAME}&repo={name}&{THEME}&cache_seconds=3600"
    return f"[![{name}]({url})](https://github.com/{USERNAME}/{name})"

def repo_grid(repos, cols=2, max_show=6):
    """Generate n-column grid of repo cards."""
    cards = [pin_card(r["name"]) for r in repos[:max_show]]
    rows = []
    for i in range(0, len(cards), cols):
        rows.append("\n".join(cards[i:i+cols]))
    return "\n\n".join(rows)

def ml_table(repos):
    """Generate ML portfolio table from actual repos."""
    if not repos:
        return "No ML repositories found."
    rows = ["| Repository | Description | Language |"]
    rows.append("|---|---|---|")
    for r in repos:
        name = r["name"]
        desc = (r.get("description") or "").split("\n")[0][:50] or name.replace("-", " ").title()
        lang = r.get("language") or "Python"
        stars = r.get("stargazers_count", 0)
        link = f"[{name}](https://github.com/{USERNAME}/{name})"
        rows.append(f"| {link} | {desc} | `{lang}` |")
    return "\n".join(rows)

# ── Main README builder ───────────────────────────────────────────────────────
def build_readme(token):
    print("📊 Fetching user profile…")
    user = get_user_data(token)

    name = user.get("name") or USERNAME
    bio = user.get("bio") or "Developer"
    location = user.get("location") or "Earth"
    public_repos = user.get("public_repos", 0)
    followers = user.get("followers", 0)
    following = user.get("following", 0)
    blog = (user.get("blog") or "").strip()
    if blog and not blog.startswith("http"):
        blog = "https://" + blog
    blog = blog or "https://github.com/" + USERNAME
    created_at = user.get("created_at", "")[:10]
    email = user.get("email") or "contact@example.com"
    linkedin = user.get("twitter_username") or USERNAME.lower()
    avatar = user.get("avatar_url", "")
    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    print("📦 Fetching repositories…")
    all_repos = get_all_repos(token)
    repos = [r for r in all_repos if not r.get("fork")]

    print(f"📌 Fetching pinned repos…")
    pinned_names = get_pinned(token)

    # Sort: pinned first, then by stars
    pinned_repos = [r for r in repos if r["name"] in pinned_names]
    other_repos = sorted(
        [r for r in repos if r["name"] not in pinned_names],
        key=lambda r: r.get("stargazers_count", 0), reverse=True
    )
    sorted_repos = pinned_repos + other_repos

    # Classify all repos
    ai_repos, ml_repos, fs_repos = [], [], []
    for r in sorted_repos:
        cat = classify(r)
        if cat == "ai":
            ai_repos.append(r)
        elif cat == "ml":
            ml_repos.append(r)
        elif cat == "fs":
            fs_repos.append(r)

    # Statistics
    total_stars = sum(r.get("stargazers_count", 0) for r in sorted_repos)
    total_forks = sum(r.get("forks_count", 0) for r in sorted_repos)

    # Top languages (auto-detected from repos)
    lang_count = {}
    for r in sorted_repos:
        l = r.get("language")
        if l:
            lang_count[l] = lang_count.get(l, 0) + 1
    top_langs = sorted(lang_count.items(), key=lambda x: -x[1])[:6]
    top_langs_str = ", ".join(f"{l}" for l, _ in top_langs) if top_langs else "Python, TypeScript"

    # Fetch contributions
    print("📊 Fetching contribution stats…")
    total_contributions = get_user_contributions(token)

    print(f"✅ Generated README for {name}")

    # Build markdown
    readme = f"""\
<div align="center">

<!-- Header Banner -->
<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=220&section=header&text={quote(name)}&fontSize=56&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Full-Stack%20Developer%20%E2%80%A2%20AI%20Builder%20%E2%80%A2%20ML%20Engineer&descSize=18&descAlignY=60&descColor=a78bfa"/>

<!-- Animated intro -->
<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=500&size=20&duration=3500&pause=1200&color=A78BFA&center=true&vCenter=true&width=800&height=50&lines=Building+AI+that+solves+real+problems.;{public_repos}+public+repos.;{total_contributions}+total+contributions.;Shipping+production+code+daily." alt="Typing SVG"/>

<br/>

<!-- Dynamic badges -->
[![Profile Views](https://komarev.com/ghpvc/?username={USERNAME}&color=7c3aed&style=flat-square&label=profile+views)](https://github.com/{USERNAME})
&nbsp;
[![Followers](https://img.shields.io/github/followers/{USERNAME}?label=followers&style=flat-square&color=7c3aed&logo=github)](https://github.com/{USERNAME}?tab=followers)
&nbsp;
[![Stars](https://img.shields.io/github/stars/{USERNAME}?label=stars&style=flat-square&color=7c3aed&logo=github)](https://github.com/{USERNAME}?tab=repositories)
&nbsp;
[![Email](https://img.shields.io/badge/Email-say%20hello-D14836?style=flat-square&logo=gmail&logoColor=white)](mailto:{email})

</div>

---

## 👨‍💻 About Me

{bio}

**Location:** {location}  
**Member Since:** {created_at}  
**Portfolio:** [{blog.split("//")[-1]}]({blog})

---

## 📊 GitHub Profile at a Glance

```yaml
name              : {name}
location          : {location}
portfolio         : {blog}
email             : {email}

stats:
  public_repos    : {public_repos}
  total_stars     : {total_stars}
  total_forks     : {total_forks}
  followers       : {followers}
  following       : {following}
  total_contributions : {total_contributions}
  member_since    : {created_at}

repo_breakdown:
  ai_apps         : {len(ai_repos)}
  ml_projects     : {len(ml_repos)}
  fullstack       : {len(fs_repos)}

top_languages   : [{top_langs_str}]
last_updated    : {generated_at}
```

---

## 🎯 Current Projects

**Active Development:**
{chr(10).join(f"- 🚀 **{r['name'].replace('-', ' ').title()}** — {r.get('description', 'Project')}" for r in sorted_repos[:3])}

---

## 📈 Live GitHub Analytics

> Real-time metrics pulled from your GitHub profile — updated on every page view

<div align="center">

<!-- Stats card: refreshes on page load -->
<img height="180em" src="{STATS_BASE}?username={USERNAME}&show_icons=true&{THEME}&rank_icon=github&cache_seconds=3600"/>

<!-- Language breakdown -->
<img height="180em" src="{STATS_BASE}/top-langs/?username={USERNAME}&layout=compact&langs_count=8&{THEME}&hide=html,css&cache_seconds=3600"/>

</div>

### 📊 Profile Metrics

<table align="center">
<tr>
<td align="center" width="25%">

**Total Contributions**

{total_contributions}

All-time

</td>
<td align="center" width="25%">

**Public Repositories**

{public_repos}

Active Projects

</td>
<td align="center" width="25%">

**Total Stars**

{total_stars}

Community Recognition

</td>
<td align="center" width="25%">

**Followers**

{followers}

Network

</td>
</tr>
</table>

<!-- Contribution streak and activity -->
<div align="center">

<img src="https://streak-stats.demolab.com?user={USERNAME}&theme=dark&hide_border=true&background=0d1117&ring=a78bfa&fire=a78bfa&currStreakLabel=e2e8f0&sideNums=a78bfa&sideLabels=94a3b8" alt="GitHub streak"/>

</div>

<div align="center">

<img src="https://github-readme-activity-graph.vercel.app/graph?username={USERNAME}&bg_color=0d1117&color=a78bfa&line=7c3aed&point=e2e8f0&area=true&hide_border=true&area_color=7c3aed&radius=6" alt="Contribution graph"/>

</div>

---

## 🚀 Featured Projects

### AI / Full-Stack Applications ({len(ai_repos)})

<div align="center">

{repo_grid(ai_repos + fs_repos, cols=2, max_show=6) if (ai_repos + fs_repos) else "No AI/FS projects yet"}

</div>

---

### Machine Learning & Data Science ({len(ml_repos)})

<div align="center">

{repo_grid(ml_repos, cols=2, max_show=6) if ml_repos else "No ML projects yet"}

</div>

{ml_table(ml_repos)}

---

## 🛠️ Tech Stack

**Languages & Frameworks:**
{", ".join(f"`{l}`" for l, _ in top_langs) if top_langs else "Python, TypeScript, JavaScript"}

---

## 🐍 Contribution Snake

> Visualization of your contribution activity — redrawn every 12 hours from your real GitHub data.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake.svg">
  <img alt="GitHub contribution snake animation" src="https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/output/github-snake-dark.svg">
</picture>
</div>

---

## 📝 Stats Summary

- **Total Public Repositories:** {public_repos}
- **Total Stars Earned:** {total_stars}
- **Total Forks:** {total_forks}
- **Total Contributions:** {total_contributions}
- **GitHub Member Since:** {created_at}
- **Following:** {following}
- **Followers:** {followers}

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=100&section=footer"/>

*🤖 Fully automated README · Last generated {generated_at}*

**[{name}](https://github.com/{USERNAME})** • [{blog.split("//")[-1]}]({blog})

</div>
"""
    return readme


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN required")
        exit(1)

    readme = build_readme(token)
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    print("✅ Fully automated README.md generated successfully!")
