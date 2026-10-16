Run make ci in the current worktree. Report lint/test results, branch and SHA,
blockers and the next checkpoint. Do not claim live integrations or product proofs
passed unless actually run. If DB is unavailable, report it and use make db-up;
never substitute SQLite or silently skip DB checks.
