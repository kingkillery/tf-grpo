from __future__ import annotations

import argparse
from pathlib import Path

from training_free_grpo.eval import EvalRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Training-Free GRPO evaluation")
    parser.add_argument("--config_name", required=True, help="Eval config path or name")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    runner = EvalRunner(args.root, args.config_name)
    metrics = runner.run()
    print(metrics)


if __name__ == "__main__":
    main()
