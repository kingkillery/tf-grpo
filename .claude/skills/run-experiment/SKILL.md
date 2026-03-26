---
name: run-experiment
description: Launch and inspect tf-grpo-upstream practice or eval workflows. Use when the task is to run an experiment, validate config wiring, check required environment variables, or summarize outputs from runs/<exp_id>.
allowed-tools: Read, Grep, Glob, Bash
---

# Run Experiment

Use this skill to operate the repo's native experiment workflow safely and consistently.

## Scope

This repository has two primary execution paths:

- `python scripts/run_training_free_GRPO.py --config_name ...`
- `python scripts/run_eval.py --config_name ...`

Use this skill when the user wants to:

- launch a practice run
- launch an eval run
- confirm config dependencies before spending API calls
- verify which environment variables are required
- inspect the resulting run artifacts under `runs/<exp_id>`

## Procedure

1. Identify whether the request is `practice` or `eval`.
2. Read the selected YAML config first.
3. Resolve referenced configs:
   - practice -> agent config and optional evaluation config
   - eval -> agent config and optional judge model
4. Infer required environment variables:
   - agent model provider `api_key_env`
   - eval judge model `api_key_env`
   - `SERPAPI_API_KEY` when `google_search` is enabled
5. Before running anything, report the exact command you will use.
6. Run only the repo-native script entry point.
7. After completion, inspect the corresponding `runs/<exp_id>` directory and summarize:
   - key metrics
   - generated files
   - final experience file
   - exported agent config when present

## Guardrails

- Do not edit files inside `runs/` except if the user explicitly asks to clean or modify generated outputs.
- Treat `configs/agents/practice/*_agent.yaml` files ending in `_agent.yaml` as generated outputs unless the user explicitly asks to modify them.
- If required environment variables are missing, stop before launch and say exactly which ones are absent.
- Prefer summarizing run artifacts over dumping raw JSON unless the user asks for the full file contents.

## Useful file surface

- `scripts/run_training_free_GRPO.py`
- `scripts/run_eval.py`
- `training_free_grpo/config.py`
- `training_free_grpo/practice.py`
- `training_free_grpo/eval.py`
- `configs/practice/*.yaml`
- `configs/eval/**/*.yaml`
- `configs/agents/practice/*.yaml`
- `runs/<exp_id>/`

## Output contract

When you use this skill, structure the response as:

1. selected mode and config
2. resolved dependencies
3. required environment variables
4. command executed
5. outcome summary
6. artifact summary
