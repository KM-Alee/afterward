"""Format only the edited Python file from a Claude PostToolUse JSON payload."""

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    payload = json.load(sys.stdin)
    raw_path = payload.get("tool_input", {}).get("file_path")
    if not raw_path:
        return 0
    root = Path(__file__).resolve().parents[1]
    path = Path(raw_path).resolve()
    if not path.is_relative_to(root) or path.suffix != ".py" or not path.is_file():
        return 0
    relative = path.relative_to(root)
    if "private" in relative.parts or any(part.startswith(".env") for part in relative.parts):
        return 0
    if path.name.startswith("client_secret"):
        return 0
    return subprocess.run(
        ["uv", "run", "--offline", "--frozen", "ruff", "format", "--", str(path)], cwd=root
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
