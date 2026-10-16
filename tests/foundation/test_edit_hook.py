"""Check that the edit hook formats only a safe in-repository Python target."""

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import format_edited_python


@pytest.mark.parametrize(
    "path",
    ["/tmp/outside.py", "README.md", "private/fixture.py", "client_secret_fixture.py", ".env.py"],
)
def test_hook_ignores_non_targets(path, monkeypatch):
    root = Path(format_edited_python.__file__).resolve().parents[1]
    candidate = Path(path) if path.startswith("/") else root / path
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(candidate)}}))
    )

    def unexpected(*args, **kwargs):
        pytest.fail("Formatter must not be invoked for this path")

    monkeypatch.setattr(format_edited_python.subprocess, "run", unexpected)
    assert format_edited_python.main() == 0


def test_hook_formats_exactly_the_edited_file(monkeypatch):
    target = Path(__file__).resolve()
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(target)}}))
    )
    calls = []

    def capture(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(format_edited_python.subprocess, "run", capture)
    assert format_edited_python.main() == 0
    assert calls[0][0] == [
        "uv",
        "run",
        "--offline",
        "--frozen",
        "ruff",
        "format",
        "--",
        str(target),
    ]
    assert calls[0][1]["cwd"] == target.parents[2]
