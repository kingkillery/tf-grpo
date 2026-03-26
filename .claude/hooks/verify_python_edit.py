from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def extract_target_path(payload: dict) -> Path | None:
    tool_input = payload.get("tool_input") or {}
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value)
    return None


def normalize_target(path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (ROOT / path).resolve()


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    target = extract_target_path(payload)
    if target is None:
        return 0

    target = normalize_target(target)
    if target.suffix != ".py" or not target.exists():
        return 0

    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return 0

    message = proc.stderr or proc.stdout or f"py_compile failed for {target}"
    sys.stderr.write(message)
    if not message.endswith("\n"):
        sys.stderr.write("\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
