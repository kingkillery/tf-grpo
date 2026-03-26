# Harness

This repository is designed to be legible to humans and to whatever automation layer is currently in use.

## System of record

- `README.md`: human entry point and run commands.
- `HARNESS.md`: repo-level harness notes, invariants, and workflow expectations.
- `configs/`: experiment configuration source of truth.
- `training_free_grpo/`: execution logic.
- `scripts/`: CLI entry points.
- `runs/`: generated outputs and step artifacts.

## Operating principles

- Prefer repo-local, versioned truth over chat history.
- Prefer deterministic checks over verbal conventions.
- Treat generated outputs as disposable unless explicitly promoted.
- Keep long-running workflows restartable from files and scripts.
- Make validation cheap enough to run on every edit.

## Long-running workflow

1. Inspect the relevant config first.
2. Resolve dependencies across linked configs and environment variables.
3. Run the smallest native script that exercises the change.
4. Inspect generated artifacts.
5. Promote repeated human judgment into docs, checks, or scripts.

## Guardrails

- `runs/` is generated output.
- `__pycache__/` and `*.egg-info/` are disposable.
- Python changes should pass `python -m py_compile`.
- Config changes should be traceable from the YAML files in `configs/`.

## Automation layers

This repo currently has a Claude-specific adapter under `.claude/`, but the harness itself is not tied to Claude.

If you replace the automation layer later, preserve:

- the repo memory in this file
- the generated-output guardrails
- the validation checks
- the experiment/run workflow conventions
