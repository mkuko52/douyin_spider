#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"

command -v git >/dev/null 2>&1 || { echo "[ERROR] Git is not installed." >&2; exit 1; }
[ -d .git ] || { echo "[ERROR] This updater requires a Git-cloned project." >&2; echo "Clone it with: git clone https://github.com/mkuko52/douyin_spider.git" >&2; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "[ERROR] Local code changes found. Commit or discard them before updating." >&2; exit 1; }

echo "Updating douyin_spider..."
git pull --ff-only origin main
echo "Update complete."
