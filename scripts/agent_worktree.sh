#!/usr/bin/env bash
set -euo pipefail
slice="${1:-}"
case "$slice" in
  foundation|engine-truth|channels-conversation|mail-integrations|web-desk-call|qa-adversary) ;;
  *) echo "Usage: $0 <foundation|engine-truth|channels-conversation|mail-integrations|web-desk-call|qa-adversary>" >&2; exit 2 ;;
esac
root="$(git rev-parse --show-toplevel)"
cd "$root"
git show-ref --verify --quiet refs/heads/main || { echo 'Local main is required.' >&2; exit 1; }
target="$(dirname "$root")/afterward-$slice"
branch="slice/$slice"
if [[ -e "$target" ]] || git show-ref --verify --quiet "refs/heads/$branch"; then
  echo 'Refusing to overwrite an existing worktree or branch.' >&2
  exit 1
fi
# Git copies tracked content only; ignored secrets and local files are never copied.
git worktree add -b "$branch" "$target" main
printf 'Created %s on %s. Run make setup there, then read AGENTS.md.\n' "$target" "$branch"
