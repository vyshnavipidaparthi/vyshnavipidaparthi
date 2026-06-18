# ─────────────────────────────────────────────────────────────────────────────
# update_readme.yml
# Auto-generates a dynamic README.md from live GitHub API data.
#
# Triggers:
#   - Every push to `main`
#   - Every 6 hours via cron schedule
#   - Manual via workflow_dispatch
#
# Portability: works on ANY GitHub profile repository without code changes.
#   The GitHub username and repository are injected dynamically at runtime
#   via GITHUB_REPOSITORY / github.actor — no hardcoding anywhere.
# ─────────────────────────────────────────────────────────────────────────────

name: Update README

on:
  push:
    branches:
      - main

  schedule:
    # Runs at minute 0 of every 6th hour: 00:00, 06:00, 12:00, 18:00 UTC
    - cron: "0 */6 * * *"

  workflow_dispatch:
    # Allows manual trigger from the Actions tab — useful for testing

# ── Minimum required permissions ─────────────────────────────────────────────
# `contents: write` is required so the workflow can commit README.md back.
# All other permissions default to `none` (principle of least privilege).
permissions:
  contents: write

jobs:
  update-readme:
    name: Generate and Commit README
    runs-on: ubuntu-latest

    steps:

      # ── 1. Checkout ──────────────────────────────────────────────────────
      # fetch-depth: 0  →  full history, so `git diff` and `git log` work
      #                    correctly and the push won't be rejected.
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      # ── 2. Python setup ───────────────────────────────────────────────────
      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # ── 3. Install dependencies ───────────────────────────────────────────
      # Only `requests` is required by generate_readme.py.
      # `--no-cache-dir` keeps the runner image clean.
      - name: Install Python dependencies
        run: pip install --no-cache-dir requests

      # ── 4. Generate README ────────────────────────────────────────────────
      # Why GITHUB_TOKEN instead of PAT_TOKEN?
      #   The script only reads public GitHub API data for the same account
      #   and writes one file back to the same repository.  The built-in
      #   GITHUB_TOKEN has exactly those permissions when `contents: write`
      #   is set above — no PAT is needed.
      #
      #   A PAT would only be necessary if the script needed to:
      #     • access private repos belonging to another user/org, OR
      #     • trigger downstream workflows in other repositories.
      #
      # GITHUB_REPOSITORY is injected so generate_readme.py can derive the
      # username without any hardcoded value (see Recommendations section).
      - name: Generate README.md
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: python generate_readme.py

      # ── 5. Commit & push (only when README actually changed) ─────────────
      # Strategy:
      #   a) Configure a bot identity for the commit author.
      #   b) Stage only README.md.
      #   c) Check `git diff --cached` — exit 0 (no diff) skips commit/push.
      #   d) Append `[skip ci]` to prevent the commit from re-triggering
      #      this workflow (infinite loop guard).
      - name: Commit and push if README changed
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          git add README.md

          # If nothing changed, exit cleanly without committing
          if git diff --cached --quiet; then
            echo "✅ README.md is already up-to-date. Nothing to commit."
            exit 0
          fi

          git commit -m "chore: auto-update README [skip ci]"
          git push
