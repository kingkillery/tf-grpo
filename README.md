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

## Run the market-research workflow

This repo can also practice on a short-horizon market-research task using the
local `MiroFish` repo as a research tool surface.

```bash
export OPENAI_API_KEY=...
python scripts/run_training_free_GRPO.py --config_name configs/practice/web_market_research.yaml
python scripts/run_eval.py --config_name configs/eval/market/web_market_research.yaml
```

Notes:

- The default market workflow now points at `examples/kalshi_market_corpus.jsonl`, exported from the local `MiroFish` repo.
- Refresh that corpus with:

```bash
cd C:\dev\Desktop-Projects\MiroFish
npm run kalshi:export-corpus -- --ticker KXHIGHNY-26MAR15-T47 --ticker KXHIGHNY-26MAR15-B47.5 --ticker KXHIGHNY-26MAR15-B49.5 --ticker KXHIGHNY-26MAR15-B51.5 --ticker KXHIGHNY-26MAR15-B53.5 --ticker KXHIGHNY-26MAR15-T54 --snapshot-hours-before-expiry 24 --period-minutes 60 --output-jsonl C:\dev\Desktop-Projects\tf-grpo-upstream\examples\kalshi_market_corpus.jsonl
```

- The current corpus is a small bootstrap dataset, so practice and eval reuse the same rows until a larger holdout split is exported.
- Reward is based on a realized-profit style verifier (`market_pnl`), not an LLM judge.
- The agent is expected to call the local script `C:\dev\Desktop-Projects\MiroFish\backend\scripts\kalshi_research_packet.py`.

## Command Center

This repo now includes a browser-based operator UI for inspecting configs, launching runs, and reviewing artifacts.

```bash
pip install -e .
streamlit run command_center.py
```

The Command Center includes:

- practice and eval launch controls that call the existing scripts
- environment readiness checks for model and search API keys
- run inspection for `runs/<exp_id>` artifacts and step telemetry
- config dependency tracing across practice, eval, and agent YAML files
- dataset previews for the JSONL inputs behind the selected config

## Harness

Repo-level harness notes live in [HARNESS.md](C:/dev/Desktop-Projects/tf-grpo-upstream/HARNESS.md), with a Claude-specific adapter in [CLAUDE.md](C:/dev/Desktop-Projects/tf-grpo-upstream/CLAUDE.md).

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
