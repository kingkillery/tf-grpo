from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import ConfigLoader
from .experience import ExperiencePool
from .llm import OpenAICompatibleLLM
from .policy import REACT_SYSTEM_PROMPT, PolicyRunner
from .prompts_math import PROBLEM_WITH_EXPERIENCE_TEMPLATE as MATH_PROMPT
from .prompts_web import PROBLEM_WITH_EXPERIENCE_TEMPLATE as WEB_PROMPT
from .tools import HttpGetTool, PythonExecTool, SerpApiSearchTool, ToolRegistry
from .utils import ensure_dir, load_jsonl, save_json, save_jsonl
from .verify import resolve_verify, verify_web_llm
from .prompts_math import SYSTEM_PROMPT as MATH_SYSTEM_PROMPT
from .prompts_web import SYSTEM_PROMPT as WEB_SYSTEM_PROMPT


class EvalRunner:
    def __init__(self, root: str | Path, config_name: str) -> None:
        self.root = Path(root)
        self.loader = ConfigLoader(self.root)
        self.cfg = self.loader.load_eval(config_name)
        self.agent_cfg = self.loader.load_agent(self.cfg.agent_config)
        self.llm = OpenAICompatibleLLM(
            model=self.agent_cfg.model_provider.model,
            api_key=self.agent_cfg.model_provider.resolve_api_key(),
            base_url=self.agent_cfg.model_provider.base_url,
        )
        if self.cfg.judge_model and self.cfg.judge_model.model_provider:
            provider = self.cfg.judge_model.model_provider
            self.judge_llm = OpenAICompatibleLLM(model=provider.model, api_key=provider.resolve_api_key(), base_url=provider.base_url)
        else:
            self.judge_llm = self.llm
        self.domain = "web" if ("web" in self.cfg.exp_id.lower() or "search" in self.cfg.exp_id.lower()) else "math"
        self.prompt_template = WEB_PROMPT if self.domain == "web" else MATH_PROMPT
        self.policy = self._build_policy()
        self.verify = resolve_verify(self.cfg.verify_type)

    def run(self) -> dict[str, Any]:
        rows = self._load_dataset(self.cfg.dataset_path)
        pool = self._load_experience_pool()
        out_dir = ensure_dir(self.root / "runs" / self.cfg.exp_id)
        results = []
        problem_to_scores: dict[str, list[float]] = {}
        tool_calls = []
        for sample in rows:
            prompt = self.prompt_template.format(experiences=pool.render() if pool else "None", problem=sample["problem"])
            scores = []
            for _ in range(self.cfg.pass_k):
                rollout = self.policy.rollout(prompt, sample["problem"], temperature=0.3, max_tokens=4096, max_steps=8)
                payload = {"problem": sample["problem"], "groundtruth": sample.get("groundtruth"), "response": rollout.response}
                if self.cfg.verify_type == "llm":
                    verdict = verify_web_llm(payload, self.judge_llm)
                else:
                    verdict = self.verify(payload, self.judge_llm)
                rollout.reward = verdict.reward
                rollout.reasoning = verdict.reasoning
                scores.append(verdict.reward)
                results.append(rollout.to_dict())
                tool_calls.append(sum(1 for step in rollout.trajectories[0]["trajectory"] if step.get("role") == "tool"))
            problem_to_scores[sample["problem"]] = scores
        save_jsonl(out_dir / "eval_rollouts.jsonl", results)
        metrics = {
            "avg_reward": sum(r.get("reward") or 0 for r in results) / max(len(results), 1),
            f"Pass@{self.cfg.pass_k}": sum(max(scores) > 0 for scores in problem_to_scores.values()) / max(len(problem_to_scores), 1),
            "avg_tool_call": sum(tool_calls) / max(len(tool_calls), 1),
        }
        save_json(out_dir / "eval_metrics.json", metrics)
        return metrics

    def _build_policy(self) -> PolicyRunner:
        tools = []
        for tool_cfg in self.agent_cfg.tools:
            if not tool_cfg.enabled:
                continue
            if tool_cfg.name == "python_exec":
                tools.append(PythonExecTool(**tool_cfg.params))
            elif tool_cfg.name == "get_content":
                tools.append(HttpGetTool(**tool_cfg.params))
            elif tool_cfg.name == "google_search":
                tools.append(SerpApiSearchTool(**tool_cfg.params))
        registry = ToolRegistry(tools)
        system_prompt = self.agent_cfg.system_prompt
        if self.agent_cfg.policy == "agent":
            task_prompt = WEB_SYSTEM_PROMPT if self.domain == "web" else MATH_SYSTEM_PROMPT
            react_prompt = REACT_SYSTEM_PROMPT.format(tool_descriptions=registry.describe())
            system_prompt = (system_prompt + "\n\n" + react_prompt) if system_prompt else (task_prompt + "\n\n" + react_prompt)
        return PolicyRunner(self.llm, mode="agent" if self.agent_cfg.policy == "agent" else "prompt", system_prompt=system_prompt, tools=registry)

    def _load_experience_pool(self):
        if getattr(self.agent_cfg, "experience_file", None):
            exp_path = Path(self.agent_cfg.experience_file)
            if not exp_path.is_absolute():
                exp_path = self.root / exp_path
            return ExperiencePool.load(exp_path)
        return None

    def _load_dataset(self, path: str | Path) -> list[dict[str, Any]]:
        path = Path(path)
        if not path.is_absolute():
            path = self.root / path
        rows = load_jsonl(path)
        return [{"problem": row.get("problem") or row.get("question") or row.get("query"), "groundtruth": row.get("groundtruth") or row.get("answer"), **row} for row in rows]
