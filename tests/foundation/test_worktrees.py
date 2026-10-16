"""Verify worktree isolation and merge refusal using disposable repositories."""

import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2]


def run(repo, *args, check=True):
    return subprocess.run(args, cwd=repo, text=True, capture_output=True, check=check)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "afterward"
    path.mkdir()
    run(path, "git", "init", "-b", "main")
    for key, value in (
        ("user.name", "Fixture"),
        ("user.email", "fixture@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", "/dev/null"),
    ):
        run(path, "git", "config", key, value)
    (path / "scripts").mkdir()
    for name in ("agent_worktree.sh", "merge_slice.sh"):
        shutil.copy(SOURCE / "scripts" / name, path / "scripts" / name)
    (path / ".gitignore").write_text("private/\n*.local.md\n")
    (path / "Makefile").write_text("setup:\n\t@true\nci:\n\t@true\n")
    run(path, "git", "add", ".")
    run(path, "git", "commit", "-m", "chore: fixture")
    return path


@pytest.mark.parametrize("slice_name", ["engine-truth", "frontend-mockup"])
def test_worktree_copies_no_ignored_files_and_validates_name(repo, slice_name):
    (repo / "private").mkdir()
    (repo / "private" / "fixture.txt").write_text("non-secret ignored fixture")
    invalid = run(repo, "bash", "scripts/agent_worktree.sh", "../bad", check=False)
    assert invalid.returncode == 2
    run(repo, "bash", "scripts/agent_worktree.sh", slice_name)
    worktree = repo.parent / f"afterward-{slice_name}"
    assert not (worktree / "private").exists()
    assert run(worktree, "git", "branch", "--show-current").stdout.strip() == f"slice/{slice_name}"
    assert run(repo, "bash", "scripts/agent_worktree.sh", slice_name, check=False).returncode


def test_failed_ci_refuses_merge_then_green_creates_merge_commit(repo):
    run(repo, "bash", "scripts/agent_worktree.sh", "engine-truth")
    worktree = repo.parent / "afterward-engine-truth"
    original = run(repo, "git", "rev-parse", "main").stdout.strip()
    (worktree / "Makefile").write_text("setup:\n\t@true\nci:\n\t@false\n")
    run(worktree, "git", "add", "Makefile")
    run(worktree, "git", "commit", "-m", "test(engine-truth): fail CI")
    failed = run(repo, "bash", "scripts/merge_slice.sh", "engine-truth", check=False)
    assert failed.returncode != 0
    assert run(repo, "git", "rev-parse", "main").stdout.strip() == original
    (worktree / "Makefile").write_text("setup:\n\t@true\nci:\n\t@true\n")
    run(worktree, "git", "add", "Makefile")
    run(worktree, "git", "commit", "-m", "test(engine-truth): restore CI")
    # Main advances after the worktree was created: merge must rebase the slice first.
    (repo / "lead.txt").write_text("lead change\n")
    run(repo, "git", "add", "lead.txt")
    run(repo, "git", "commit", "-m", "chore: lead update")
    lead = run(repo, "git", "rev-parse", "main").stdout.strip()
    run(repo, "bash", "scripts/merge_slice.sh", "engine-truth")
    parents = run(repo, "git", "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(parents) == 3
    assert parents[1] == lead
    assert (worktree / "lead.txt").exists()
