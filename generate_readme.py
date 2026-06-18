#!/usr/bin/env python3
"""
generate_readme.py — Premium GitHub Profile README Generator
─────────────────────────────────────────────────────────────
Features
  • Zero hardcoding — username resolved from GITHUB_REPOSITORY at runtime
  • REST + GraphQL hybrid for maximum data richness
  • Exponential-backoff retry with jitter on 429 / 5xx
  • Structured logging with emoji-prefixed levels
  • Keyword-based repo classifier (AI / ML / Full-Stack / Other)
  • Visually premium Markdown with capsule banners, stat widgets,
    contribution snake, streak card, and activity graph
  • Idempotent — exits 0 and skips write when README is unchanged

Environment variables (set by GitHub Actions)
  GITHUB_TOKEN       required — actions token or PAT
  GITHUB_REPOSITORY  required — "owner/repo" format
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

LOG_ICONS = {
    logging.DEBUG:    "🔍",
    logging.INFO:     "✅",
    logging.WARNING:  "⚠️ ",
    logging.ERROR:    "❌",
    logging.CRITICAL: "💥",
}


class _PrettyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        icon = LOG_ICONS.get(record.levelno, "•")
        ts = datetime.now().strftime("%H:%M:%S")
        return f"[{ts}] {icon}  {record.getMessage()}"


def _make_logger() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_PrettyFormatter())
    logger = logging.getLogger("readme_gen")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


log = _make_logger()

# ══════════════════════════════════════════════════════════════════════════════
# Environment & configuration
# ══════════════════════════════════════════════════════════════════════════════

def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        log.critical(f"Required environment variable '{name}' is missing or empty.")
        sys.exit(1)
    return value


_raw_repo = _require_env("GITHUB_REPOSITORY")   # "owner/repo"
TOKEN      = _require_env("GITHUB_TOKEN")

if "/" not in _raw_repo:
    log.critical(f"GITHUB_REPOSITORY must be 'owner/repo', got: {_raw_repo!r}")
    sys.exit(1)

USERNAME = _raw_repo.split("/")[0]

GITHUB_REST_API    = "https://api.github.com"
GITHUB_GRAPHQL_API = "https://api.github.com/graphql"

OUTPUT_FILE = "README.md"

# ══════════════════════════════════════════════════════════════════════════════
# HTTP client with retry / back-off
# ══════════════════════════════════════════════════════════════════════════════

_SESSION = requests.Session()
_SESSION.headers.update({
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "readme-generator/2.0",
})

_RETRY_STATUSES  = {429, 500, 502, 503, 504}
_MAX_RETRIES     = 4
_BASE_BACKOFF_S  = 1.5


def _rest(endpoint: str, *, params: dict | None = None) -> Any:
    """
    GET GitHub REST API endpoint with exponential-backoff retry.
    Returns parsed JSON or raises on unrecoverable error.
    """
    url = f"{GITHUB_REST_API}{endpoint}"

    for attempt in range(_MAX_RETRIES):
        try:
            r = _SESSION.get(url, params=params, timeout=20)

            if r.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                wait = _BASE_BACKOFF_S * (2 ** attempt) + random.uniform(0, 0.5)
                log.warning(f"HTTP {r.status_code} — retrying in {wait:.1f}s (attempt {attempt+1}/{_MAX_RETRIES})")
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r.json()

        except requests.exceptions.Timeout:
            if attempt < _MAX_RETRIES - 1:
                wait = _BASE_BACKOFF_S * (2 ** attempt)
                log.warning(f"Timeout — retrying in {wait:.1f}s")
                time.sleep(wait)
            else:
                log.error(f"Persistent timeout for {url}")
                return {} if "user" in endpoint else []

        except requests.exceptions.RequestException as exc:
            log.error(f"Request failed for {url}: {exc}")
            return {} if "user" in endpoint else []

    return {} if "user" in endpoint else []


def _graphql(query: str) -> dict:
    """
    POST GitHub GraphQL API with the same retry strategy.
    Returns the 'data' key from the response.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            r = _SESSION.post(
                GITHUB_GRAPHQL_API,
                json={"query": query},
                timeout=20,
            )

            if r.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                wait = _BASE_BACKOFF_S * (2 ** attempt) + random.uniform(0, 0.5)
                log.warning(f"GraphQL HTTP {r.status_code} — retrying in {wait:.1f}s")
                time.sleep(wait)
                continue

            r.raise_for_status()
            payload = r.json()

            if "errors" in payload:
                for err in payload["errors"]:
                    log.warning(f"GraphQL error: {err.get('message', err)}")

            return payload.get("data", {})

        except requests.exceptions.RequestException as exc:
            if attempt < _MAX_RETRIES - 1:
                wait = _BASE_BACKOFF_S * (2 ** attempt)
                log.warning(f"GraphQL request failed, retrying: {exc}")
                time.sleep(wait)
            else:
                log.error(f"GraphQL permanently failed: {exc}")
                return {}

    return {}

# ══════════════════════════════════════════════════════════════════════════════
# Data fetchers
# ══════════════════════════════════════════════════════════════════════════════

def fetch_profile() -> dict:
    log.info(f"Fetching profile for @{USERNAME} …")
    return _rest(f"/users/{USERNAME}")


def fetch_repos() -> list[dict]:
    """Paginate through all non-forked repos owned by USERNAME."""
    log.info("Fetching repositories …")
    all_repos: list[dict] = []
    page = 1
    while page <= 10:                        # safety ceiling: 1 000 repos
        batch = _rest(
            f"/users/{USERNAME}/repos",
            params={"per_page": 100, "type": "owner", "sort": "updated", "page": page},
        )
        if not batch:
            break
        all_repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    owned = [r for r in all_repos if not r.get("fork")]
    log.info(f"Found {len(owned)} owned repos (from {len(all_repos)} total)")
    return owned


def fetch_graphql_stats() -> dict:
    """Single GraphQL call that pulls contribution totals + pinned repos."""
    log.info("Fetching GraphQL stats (contributions + pinned repos) …")
    query = f"""
    {{
      user(login: "{USERNAME}") {{
        contributionsCollection {{
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalRepositoryContributions
          contributionCalendar {{
            totalContributions
          }}
        }}
        pullRequests(states: MERGED) {{
          totalCount
        }}
        issues {{
          totalCount
        }}
        pinnedItems(first: 6, types: REPOSITORY) {{
          nodes {{
            ... on Repository {{
              name
              description
              url
              primaryLanguage {{ name }}
              stargazerCount
              forkCount
            }}
          }}
        }}
      }}
    }}
    """
    return _graphql(query).get("user", {})

# ══════════════════════════════════════════════════════════════════════════════
# Repo classification
# ══════════════════════════════════════════════════════════════════════════════

_ML_KEYWORDS = {
    "predict", "classif", "regress", "neural", "train", "model",
    "cancer", "diabetes", "fraud", "spam", "mnist", "cnn", "rnn",
    "lstm", "nlp", "sentiment", "iris", "titanic", "stock", "knn",
    "xgboost", "sklearn", "tensorflow", "pytorch", "huggingface",
    "data-science", "machine-learning", "deep-learning", "ai-model",
}

_AI_KEYWORDS = {
    "agent", "assistant", "chatbot", "rag", "gpt", "lms",
    "openai", "llm", "langchain", "claude", "copilot",
}

_FS_KEYWORDS = {
    "portfolio", "website", "frontend", "dashboard", "ui", "app",
    "fullstack", "landing", "blog", "api", "backend", "service",
    "react", "nextjs", "vue", "angular", "django", "flask", "fastapi",
}

_FS_LANGUAGES = {"typescript", "javascript", "dart"}


def _classify(repo: dict) -> str:
    blob = " ".join([
        repo.get("name", ""),
        repo.get("description") or "",
        " ".join(repo.get("topics", [])),
    ]).lower()
    lang = (repo.get("language") or "").lower()

    if any(kw in blob for kw in _AI_KEYWORDS):
        return "ai"
    if any(kw in blob for kw in _ML_KEYWORDS) or lang == "python":
        return "ml"
    if any(kw in blob for kw in _FS_KEYWORDS) or lang in _FS_LANGUAGES:
        return "fs"
    return "other"

# ══════════════════════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RepoGroup:
    ai:    list[dict] = field(default_factory=list)
    ml:    list[dict] = field(default_factory=list)
    fs:    list[dict] = field(default_factory=list)
    other: list[dict] = field(default_factory=list)

    def classify_all(self, repos: list[dict]) -> None:
        for r in repos:
            getattr(self, _classify(r)).append(r)


@dataclass
class ProfileData:
    # identity
    username:     str
    name:         str
    bio:          str
    location:     str
    blog:         str
    email:        str
    avatar:       str
    created_at:   str
    # counts
    followers:    int
    following:    int
    public_repos: int
    # repo aggregates
    total_stars:  int
    total_forks:  int
    # contributions
    total_contributions: int
    merged_prs:   int
    issues_opened: int
    # repo groups
    groups:       RepoGroup
    top_langs:    list[tuple[str, int]]
    pinned:       list[dict]
    # meta
    generated_at: str

# ══════════════════════════════════════════════════════════════════════════════
# Data assembly
# ══════════════════════════════════════════════════════════════════════════════

def assemble_data() -> ProfileData:
    profile  = fetch_profile()
    repos    = fetch_repos()
    gql      = fetch_graphql_stats()

    # Canonical blog URL
    blog = (profile.get("blog") or "").strip()
    if blog and not blog.startswith("http"):
        blog = "https://" + blog

    # Language frequency map
    lang_freq: dict[str, int] = {}
    for r in repos:
        l = r.get("language")
        if l:
            lang_freq[l] = lang_freq.get(l, 0) + 1
    top_langs = sorted(lang_freq.items(), key=lambda x: -x[1])[:8]

    # Repo groups
    groups = RepoGroup()
    groups.classify_all(repos)

    # Contribution stats
    contrib_coll = gql.get("contributionsCollection", {})
    total_contributions = (
        contrib_coll.get("contributionCalendar", {}).get("totalContributions", 0)
    )
    merged_prs    = gql.get("pullRequests", {}).get("totalCount", 0)
    issues_opened = gql.get("issues", {}).get("totalCount", 0)

    # Pinned repos
    pinned_nodes = gql.get("pinnedItems", {}).get("nodes", [])

    return ProfileData(
        username     = USERNAME,
        name         = profile.get("name") or USERNAME,
        bio          = profile.get("bio") or "Developer",
        location     = profile.get("location") or "Earth",
        blog         = blog,
        email        = profile.get("email") or "",
        avatar       = profile.get("avatar_url") or "",
        created_at   = profile.get("created_at", "")[:10],
        followers    = profile.get("followers", 0),
        following    = profile.get("following", 0),
        public_repos = profile.get("public_repos", 0),
        total_stars  = sum(r.get("stargazers_count", 0) for r in repos),
        total_forks  = sum(r.get("forks_count", 0) for r in repos),
        total_contributions = total_contributions,
        merged_prs   = merged_prs,
        issues_opened= issues_opened,
        groups       = groups,
        top_langs    = top_langs,
        pinned       = pinned_nodes,
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

# ══════════════════════════════════════════════════════════════════════════════
# Markdown builders
# ══════════════════════════════════════════════════════════════════════════════

_STATS_API  = "https://github-readme-stats.vercel.app/api"
_THEME_CORE = (
    "theme=github_dark_dimmed"
    "&hide_border=true"
    "&title_color=a78bfa"
    "&icon_color=a78bfa"
    "&text_color=e2e8f0"
    "&bg_color=0d1117"
)


def _shield(label: str, value: str, color: str = "7c3aed") -> str:
    enc_label = quote(label)
    enc_value = quote(str(value))
    return f"![{label}](https://img.shields.io/badge/{enc_label}-{enc_value}-{color}?style=flat-square)"


def _pin_card(repo_name: str, username: str) -> str:
    url = (
        f"{_STATS_API}/pin/?username={username}&repo={repo_name}"
        f"&{_THEME_CORE}&cache_seconds=3600"
    )
    return f"[![{repo_name}]({url})](https://github.com/{username}/{repo_name})"


def _repo_grid(repos: list[dict], username: str, cols: int = 2, limit: int = 6) -> str:
    if not repos:
        return "_No repositories in this category yet._"
    cards = [_pin_card(r["name"], username) for r in repos[:limit]]
    rows: list[str] = []
    for i in range(0, len(cards), cols):
        rows.append("\t".join(cards[i:i + cols]))
    return "\n\n".join(rows)


def _ml_table(repos: list[dict], username: str) -> str:
    if not repos:
        return "_No ML repositories found._"
    lines = [
        "| Repository | Description | Language | ⭐ |",
        "|:---|:---|:---:|:---:|",
    ]
    for r in repos:
        name  = r["name"]
        desc  = (r.get("description") or "").split("\n")[0][:55] or name.replace("-", " ").title()
        lang  = r.get("language") or "Python"
        stars = r.get("stargazers_count", 0)
        link  = f"[`{name}`](https://github.com/{username}/{name})"
        lines.append(f"| {link} | {desc} | `{lang}` | {stars} |")
    return "\n".join(lines)


def _typing_svg(lines: list[str]) -> str:
    encoded = ";".join(quote(l) for l in lines)
    return (
        f"[![Typing SVG](https://readme-typing-svg.demolab.com"
        f"?font=JetBrains+Mono&weight=600&size=18&duration=3200"
        f"&pause=1000&color=A78BFA&center=true&vCenter=true"
        f"&width=700&height=45&lines={encoded})]"
        f"(https://github.com/{USERNAME})"
    )


def _lang_badges(top_langs: list[tuple[str, int]]) -> str:
    # Using shields.io for each detected language
    colour_map = {
        "Python":     "3776AB", "TypeScript": "3178C6", "JavaScript": "F7DF1E",
        "Go":         "00ADD8", "Rust":       "DEA584", "Java":       "007396",
        "Kotlin":     "7F52FF", "Swift":      "FA7343", "C++":        "00599C",
        "C":          "555555", "Ruby":       "CC342D", "PHP":        "777BB4",
        "Dart":       "0175C2", "Shell":      "4EAA25", "HTML":       "E34F26",
        "CSS":        "1572B6", "Scala":      "DC322F", "R":          "276DC3",
    }
    badges: list[str] = []
    for lang, _ in top_langs:
        colour = colour_map.get(lang, "555555")
        logo   = lang.lower().replace("+", "p").replace("#", "sharp").replace(" ", "")
        badge  = (
            f"![{lang}](https://img.shields.io/badge/{quote(lang)}-{colour}"
            f"?style=for-the-badge&logo={logo}&logoColor=white)"
        )
        badges.append(badge)
    return "\n".join(badges)

# ══════════════════════════════════════════════════════════════════════════════
# README template
# ══════════════════════════════════════════════════════════════════════════════

def render_readme(d: ProfileData) -> str:
    u = d.username  # shorthand

    # Derive safe subtitle for capsule-render (200 char limit)
    safe_bio = quote(d.bio[:60]) if d.bio else "Developer"

    # Blog display text
    blog_display = d.blog.replace("https://", "").replace("http://", "").rstrip("/") if d.blog else ""

    # Typing lines
    typing_lines = [
        f"Hi, I'm {d.name} 👋",
        f"{d.public_repos} public repos · {d.total_stars} ⭐ earned",
        f"{d.total_contributions} contributions this year",
        "Shipping real products · Learning every day",
    ]

    # Active project bullets (top 3 by stars, non-empty description)
    active = [
        r for r in
        sorted(d.groups.ai + d.groups.fs + d.groups.ml, key=lambda x: -x.get("stargazers_count", 0))
        if r.get("description")
    ][:3]

    active_bullets = "\n".join(
        f"- 🚀 **[{r['name']}](https://github.com/{u}/{r['name']})** — {r['description']}"
        for r in active
    ) or "_No active projects found._"

    # Language badges block
    lang_badges = _lang_badges(d.top_langs)

    # Repo grids
    ai_grid = _repo_grid(d.groups.ai + d.groups.fs, u, cols=2, limit=6)
    ml_grid = _repo_grid(d.groups.ml,                u, cols=2, limit=6)
    ml_tbl  = _ml_table(d.groups.ml,                 u)

    # Pinned section
    if d.pinned:
        pinned_grid = _repo_grid(
            [{"name": p["name"]} for p in d.pinned], u, cols=2, limit=6
        )
        pinned_section = f"""
## 📌 Pinned Repositories

<div align="center">

{pinned_grid}

</div>
"""
    else:
        pinned_section = ""

    # Stats summary table rows
    stat_rows = [
        ("Public Repositories", d.public_repos),
        ("Total Stars Earned",  d.total_stars),
        ("Total Forks",         d.total_forks),
        ("Merged Pull Requests",d.merged_prs),
        ("Issues Opened",       d.issues_opened),
        ("Total Contributions", d.total_contributions),
        ("Followers",           d.followers),
        ("Following",           d.following),
        ("Member Since",        d.created_at),
    ]
    stat_table_rows = "\n".join(
        f"| {label} | **{value}** |" for label, value in stat_rows
    )

    # Social links row
    social_parts: list[str] = [
        f"[![GitHub](https://img.shields.io/badge/GitHub-{u}-181717?style=flat-square&logo=github)](https://github.com/{u})",
    ]
    if d.blog:
        social_parts.append(
            f"[![Portfolio](https://img.shields.io/badge/Portfolio-{quote(blog_display)}-7c3aed?style=flat-square&logo=vercel)](https://github.com/{u})"
            if not d.blog else
            f"[![Portfolio](https://img.shields.io/badge/Portfolio-website-7c3aed?style=flat-square&logo=vercel)]({d.blog})"
        )
    if d.email:
        social_parts.append(
            f"[![Email](https://img.shields.io/badge/Email-contact-D14836?style=flat-square&logo=gmail)]"
            f"(mailto:{d.email})"
        )
    social_badges = "\n".join(social_parts)

    readme = f"""\
<div align="center">

<!-- ═══ Hero Banner ═══════════════════════════════════════════════════════ -->
<img
  width="100%"
  src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,40:302b63,100:24243e&height=230&section=header&text={quote(d.name)}&fontSize=58&fontColor=ffffff&animation=fadeIn&fontAlignY=36&desc={safe_bio}&descSize=18&descAlignY=56&descColor=a78bfa"
  alt="{d.name}"
/>

<!-- ═══ Animated intro line ════════════════════════════════════════════════ -->
{_typing_svg(typing_lines)}

<br/>

<!-- ═══ Dynamic profile badges ════════════════════════════════════════════ -->
[![Profile Views](https://komarev.com/ghpvc/?username={u}&color=7c3aed&style=flat-square&label=profile+views)](https://github.com/{u})&nbsp;
[![Stars](https://img.shields.io/github/stars/{u}?label=total+stars&style=flat-square&color=7c3aed&logo=github)](https://github.com/{u}?tab=repositories)&nbsp;
[![Followers](https://img.shields.io/github/followers/{u}?label=followers&style=flat-square&color=7c3aed&logo=github)](https://github.com/{u}?tab=followers)

</div>

---

## 👤 About Me

{d.bio}

| | |
|:---|:---|
| 📍 Location | {d.location} |
| 🗓️ GitHub Since | {d.created_at} |
{f"| 🌐 Portfolio | [{blog_display}]({d.blog}) |" if d.blog else ""}
{f"| ✉️  Email | [{d.email}](mailto:{d.email}) |" if d.email else ""}

<br/>

{social_badges}

---

## 📊 GitHub Dashboard

```yaml
# Live profile snapshot — regenerated every 6 hours
github_user:
  username       : "{u}"
  location       : "{d.location}"
  member_since   : {d.created_at}
  public_repos   : {d.public_repos}

activity:
  total_contributions : {d.total_contributions}
  merged_pull_requests: {d.merged_prs}
  issues_opened       : {d.issues_opened}

repository_stats:
  total_stars  : {d.total_stars}
  total_forks  : {d.total_forks}
  ai_and_apps  : {len(d.groups.ai)}
  ml_projects  : {len(d.groups.ml)}
  fullstack    : {len(d.groups.fs)}
  other        : {len(d.groups.other)}

top_languages: [{", ".join(l for l, _ in d.top_langs)}]

network:
  followers : {d.followers}
  following : {d.following}

last_updated: "{d.generated_at}"
```

---

## 🎯 Active Projects

{active_bullets}

---

## 📈 Live Analytics

<div align="center">

<img
  height="180"
  src="{_STATS_API}?username={u}&show_icons=true&{_THEME_CORE}&rank_icon=github&cache_seconds=3600"
  alt="GitHub Stats"
/>

<img
  height="180"
  src="{_STATS_API}/top-langs/?username={u}&layout=compact&langs_count=8&{_THEME_CORE}&hide=html,css&cache_seconds=3600"
  alt="Top Languages"
/>

</div>

<div align="center">

<img
  src="https://streak-stats.demolab.com?user={u}&theme=dark&hide_border=true&background=0d1117&ring=a78bfa&fire=a78bfa&currStreakLabel=e2e8f0&sideNums=a78bfa&sideLabels=94a3b8"
  alt="Contribution Streak"
/>

</div>

<div align="center">

<img
  src="https://github-readme-activity-graph.vercel.app/graph?username={u}&bg_color=0d1117&color=a78bfa&line=7c3aed&point=e2e8f0&area=true&area_color=7c3aed&hide_border=true&radius=6"
  alt="Contribution Activity Graph"
/>

</div>

---

## 🚀 Featured Projects

### 🤖 AI & Full-Stack Applications ({len(d.groups.ai + d.groups.fs)})

<div align="center">

{ai_grid}

</div>

---

### 🧠 Machine Learning & Data Science ({len(d.groups.ml)})

<div align="center">

{ml_grid}

</div>

{ml_tbl}

---
{pinned_section}

## 🛠️ Tech Stack

{lang_badges}

---

## 📊 Profile Summary

| Metric | Value |
|:-------|------:|
{stat_table_rows}

---

## 🐍 Contribution Snake

<div align="center">

<picture>
  <source
    media="(prefers-color-scheme: dark)"
    srcset="https://raw.githubusercontent.com/{u}/{u}/output/github-snake-dark.svg">
  <source
    media="(prefers-color-scheme: light)"
    srcset="https://raw.githubusercontent.com/{u}/{u}/output/github-snake.svg">
  <img
    alt="GitHub contribution snake animation"
    src="https://raw.githubusercontent.com/{u}/{u}/output/github-snake-dark.svg">
</picture>

</div>

---

<div align="center">

<img
  width="100%"
  src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,40:302b63,100:24243e&height=100&section=footer"
  alt="footer"
/>

*🤖 Auto-generated · Last updated **{d.generated_at}***

**[{d.name}](https://github.com/{u})**{f" · [{blog_display}]({d.blog})" if d.blog else ""}

</div>
"""
    return readme

# ══════════════════════════════════════════════════════════════════════════════
# Write with idempotency guard
# ══════════════════════════════════════════════════════════════════════════════

def write_if_changed(content: str, path: str) -> bool:
    """
    Write `content` to `path` only if the file content has changed.
    Returns True if the file was written, False if it was already up-to-date.
    """
    try:
        with open(path, encoding="utf-8") as f:
            existing = f.read()
        if existing == content:
            return False
    except FileNotFoundError:
        pass

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True

# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    log.info(f"Starting README generation for @{USERNAME}")

    data   = assemble_data()
    readme = render_readme(data)

    changed = write_if_changed(readme, OUTPUT_FILE)

    if changed:
        log.info(f"README.md written successfully ({len(readme):,} chars).")
    else:
        log.info("README.md is unchanged — skipping write.")
        # Signal to the workflow that nothing needs committing.
        # The commit step uses `git diff --cached` anyway, but this log
        # makes the intent explicit for debugging.

    log.info("Done.")


if __name__ == "__main__":
    main()
