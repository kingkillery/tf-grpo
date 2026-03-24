# Training-Free GRPO Reproduction Bundle

This is a **more faithful reproduction-oriented implementation** of the Training-Free GRPO paper and the public Youtu-Agent branch structure.

It is intentionally not just a generic trainer. It includes:

- a **practice loop** with **epoch/batch/step directories**
- **grouped rollouts** (`grpo_n`)
- **trajectory summarization**
- **single-query critique / experience extraction**
- **batch-level experience consolidation**
- **math** and **web** domain prompt stacks
- **YAML configs** inspired by the official `configs/practice`, `configs/eval`, and `configs/agents/practice` layout
- **run scripts** matching the repo-style workflow:
  - `scripts/run_training_free_GRPO.py`
  - `scripts/run_eval.py`
- export of an **enhanced agent config** after practice

## Install

```bash
cd training_free_grpo_repro
pip install -e .
```

## Layout

```text
training_free_grpo_repro/
├── configs/
│   ├── agents/practice/
│   ├── eval/
│   └── practice/
├── examples/
├── scripts/
└── training_free_grpo/
```

## Run the math workflow

```bash
export DEEPSEEK_API_KEY=...
python scripts/run_eval.py --config_name configs/eval/math/math_AIME24.yaml
python scripts/run_training_free_GRPO.py --config_name configs/practice/math_reasoning.yaml
python scripts/run_eval.py --config_name configs/eval/math/math_practice_AIME24.yaml
```

## Run the web workflow

```bash
export OPENAI_API_KEY=...
export SERPAPI_API_KEY=...
python scripts/run_eval.py --config_name configs/eval/web/web.yaml
python scripts/run_training_free_GRPO.py --config_name configs/practice/web_search.yaml
python scripts/run_eval.py --config_name configs/eval/web/web_practice.yaml
```

## What is faithful to the paper / public branch

- The policy stays **frozen** and learns via an external **experience pool**.
- Rollouts are generated in **groups** and only mixed-quality groups drive updates.
- The update pipeline is **summarize → critique / extract experiences → batch consolidation**.
- The math prompts are derived directly from the paper appendix.
- The config and script structure mirrors the public Youtu-Agent practice flow.

## What is still an engineering choice

- Tool use is implemented with a **structured JSON tool protocol** for reliability.
- Web prompts are reconstructed from the public branch prompt files and normalized for readability.
- The OpenAI-compatible backend is generic, so the same code can target OpenAI-compatible providers and self-hosted endpoints.

## Outputs

A practice run writes:

- `runs/<exp_id>/epoch_XX/shuffled_data.jsonl`
- `runs/<exp_id>/step_XXX/rollout.jsonl`
- `runs/<exp_id>/step_XXX/single_rollout_summary.json`
- `runs/<exp_id>/step_XXX/single_query_critique.json`
- `runs/<exp_id>/step_XXX/group_update.json` (web)
- `runs/<exp_id>/step_XXX/batch_update.json`
- `runs/<exp_id>/step_XXX/experiences.json`
- `runs/<exp_id>/experiences_final.json`
- `configs/agents/practice/<exp_id>_agent.yaml`

## Notes

- The included datasets are **toy examples** so the pipeline is runnable without the original research datasets.
- For a serious reproduction, replace the datasets in `examples/` with your own JSONL files.
- The math verifier uses exact / symbolic matching when possible. The web verifier uses an LLM judge.
