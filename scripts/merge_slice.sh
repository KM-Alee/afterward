#!/usr/bin/env bash
set -euo pipefail
slice="${1:-}"
case "$slice" in
  foundation|frontend-mockup|engine-truth|channels-conversation|mail-integrations|web-desk-call|qa-adversary) ;;
  *) echo "Usage: $0 <foundation|frontend-mockup|engine-truth|channels-conversation|mail-integrations|web-desk-call|qa-adversary>" >&2; exit 2 ;;
esac
root="$(git rev-parse --show-toplevel)"
cd "$root"
[[ "$(git branch --show-current)" == main ]] || { echo 'Run merge from main.' >&2; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=normal)" ]] || { echo 'Main must be clean.' >&2; exit 1; }
# Serialize all merge invocations across worktrees, including rebase and verification.
common="$(git rev-parse --git-common-dir)"
exec 9>"$common/afterward-merge.lock"
flock -n 9 || { echo 'Another merge is in progress.' >&2; exit 1; }
branch="slice/$slice"
target="$(dirname "$root")/afterward-$slice"
[[ -d "$target" ]] || { echo 'Expected slice worktree is missing.' >&2; exit 1; }
[[ "$(git -C "$target" branch --show-current)" == "$branch" ]] || { echo 'Wrong slice branch.' >&2; exit 1; }
[[ -z "$(git -C "$target" status --porcelain --untracked-files=normal)" ]] || { echo 'Slice must be clean.' >&2; exit 1; }
[[ "$(git -C "$target" rev-parse --path-format=absolute --git-common-dir)" == "$(git rev-parse --path-format=absolute --git-common-dir)" ]] || { echo 'Not a worktree of this repository.' >&2; exit 1; }
main_sha="$(git rev-parse main)"
# Conflicts deliberately stop for lead review; never auto-resolve or force-push.
git -C "$target" rebase main
slice_sha="$(git rev-parse "$branch")"
(cd "$target" && make setup && make ci)
[[ -z "$(git -C "$target" status --porcelain --untracked-files=normal)" ]] || { echo 'Checks changed slice files; commit them and retry.' >&2; exit 1; }
[[ "$(git rev-parse main)" == "$main_sha" && "$(git rev-parse "$branch")" == "$slice_sha" ]] || { echo 'A branch moved during checks; retry.' >&2; exit 1; }
# Recheck the main worktree immediately before merging the tested commit.
[[ "$(git branch --show-current)" == main && -z "$(git status --porcelain --untracked-files=normal)" ]] || { echo 'Main changed during checks.' >&2; exit 1; }
git merge --no-ff "$branch" -m "chore($slice): merge verified slice"
