from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "README.md": ROOT / "README.md",
    "HARNESS.md": ROOT / "HARNESS.md",
    "CLAUDE.md": ROOT / "CLAUDE.md",
}


def main() -> int:
    missing = [name for name, path in FILES.items() if not path.exists()]
    if missing:
        print(f"Missing required docs: {', '.join(missing)}", file=sys.stderr)
        return 2

    harness = FILES["HARNESS.md"].read_text(encoding="utf-8")
    claude = FILES["CLAUDE.md"].read_text(encoding="utf-8")
    readme = FILES["README.md"].read_text(encoding="utf-8")

    errors: list[str] = []
    if "system of record" not in harness.lower():
        errors.append("HARNESS.md should describe the repo system of record.")
    claude_text = claude.lower()
    if "adapter layer" not in claude_text and "adapter-only" not in claude_text:
        errors.append("CLAUDE.md should stay adapter-only.")
    if "command center" not in readme.lower():
        errors.append("README.md should mention the command center workflow.")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    print("Harness docs are fresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
