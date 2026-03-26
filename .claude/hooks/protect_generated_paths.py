from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTECTED_ROOT_NAMES = {"runs", "__pycache__"}


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


def is_generated_agent(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return False
    rel_posix = rel.as_posix()
    return rel_posix.startswith("configs/agents/practice/") and rel.name.endswith("_agent.yaml")


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
    try:
        rel = target.relative_to(ROOT)
    except ValueError:
        return 0

    if any(part in PROTECTED_ROOT_NAMES for part in rel.parts) or is_generated_agent(target):
        sys.stderr.write(
            "Blocked edit to generated artifact. Avoid writing inside runs/, __pycache__/, "
            "or generated *_agent.yaml files unless you are intentionally regenerating them.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
