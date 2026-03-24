from __future__ import annotations

import argparse
from pathlib import Path

from training_free_grpo.practice import PracticeRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Training-Free GRPO practice")
    parser.add_argument("--config_name", required=True, help="Practice config path or name")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    runner = PracticeRunner(args.root, args.config_name)
    final_path = runner.run()
    print(final_path)


if __name__ == "__main__":
    main()
