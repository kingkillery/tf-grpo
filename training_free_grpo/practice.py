from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from .config import AgentConfig, ConfigLoader, EvalConfig, PracticeConfig
from .experience import ExperiencePool, Operation
from .llm import Message, OpenAICompatibleLLM
from .policy import REACT_SYSTEM_PROMPT, PolicyRunner, Rollout
from .prompts_math import (
    BATCH_EXPERIENCE_UPDATE_TEMPLATE,
    PROBLEM_WITH_EXPERIENCE_TEMPLATE as MATH_PROMPT,
    SINGLE_QUERY_CRITIQUE_NO_GT_TEMPLATE,
    SINGLE_QUERY_CRITIQUE_TEMPLATE,
    SINGLE_ROLLOUT_SUMMARY_NO_GT_TEMPLATE,
    SINGLE_ROLLOUT_SUMMARY_TEMPLATE,
    SYSTEM_PROMPT as MATH_SYSTEM_PROMPT,
)
from .prompts_web import (
    BATCH_EXPERIENCE_UPDATE_TEMPLATE_SP,
    BATCH_EXPERIENCE_UPDATE_TEMPLATE_UP,
    GROUP_EXPERIENCE_UPDATE_TEMPLATE_SP,
    GROUP_EXPERIENCE_UPDATE_TEMPLATE_UP,
    PROBLEM_WITH_EXPERIENCE_TEMPLATE as WEB_PROMPT,
    SINGLE_QUERY_CRITIQUE_TEMPLATE_SP,
    SINGLE_QUERY_CRITIQUE_TEMPLATE_UP,
    SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP,
    SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP,
    SYSTEM_PROMPT as WEB_SYSTEM_PROMPT,
)
from .tools import HttpGetTool, PythonExecTool, SerpApiSearchTool, ToolRegistry
from .utils import ensure_dir, extract_json, load_jsonl, save_json, save_jsonl
from .verify import VerificationResult, resolve_verify, verify_web_llm


@dataclass(slots=True)
class StepStats:
    avg_reward: float
    pass_at_k: float
    avg_tool_calls: float

    def to_dict(self) -> dict[str, float]:
        return {
            "avg_reward": self.avg_reward,
            "pass_at_k": self.pass_at_k,
            "avg_tool_calls": self.avg_tool_calls,
        }


class PracticeRunner:
    def __init__(self, root: str | Path, config_name: str) -> None:
        self.root = Path(root)
        self.loader = ConfigLoader(self.root)
        self.cfg: PracticeConfig = self.loader.load_practice(config_name)
        self.agent_cfg: AgentConfig = self.loader.load_agent(self.cfg.agent_config)
        self.eval_cfg: Optional[EvalConfig] = self.loader.load_eval(self.cfg.evaluation_config) if self.cfg.evaluation_config else None
        self.llm = OpenAICompatibleLLM(
            model=self.agent_cfg.model_provider.model,
            api_key=self.agent_cfg.model_provider.resolve_api_key(),
            base_url=self.agent_cfg.model_provider.base_url,
        )
        self.judge_llm = self._build_judge_llm()
        self.domain = "web" if ("web" in self.cfg.exp_id.lower() or "search" in self.cfg.exp_id.lower()) else "math"
        self.prompt_template = WEB_PROMPT if self.domain == "web" else MATH_PROMPT
        self.policy = self._build_policy()
        self.verify = resolve_verify(self.cfg.practice.reward)
        self.seed = 42

    def run(self) -> Path:
        run_dir = ensure_dir(self.root / "runs" / self.cfg.exp_id)
        dataset = self._load_dataset(self.cfg.data.practice_dataset_path)
        save_json(run_dir / "practice_config_resolved.json", self._resolved_config_payload())
        pool = ExperiencePool(word_limit=self.cfg.practice.experience_word_limit)
        stats: dict[str, Any] = {}
        step_counter = 0

        for epoch in range(self.cfg.practice.epochs):
            rng = random.Random(self.seed + epoch)
            shuffled = dataset[:]
            rng.shuffle(shuffled)
            epoch_dir = ensure_dir(run_dir / f"epoch_{epoch:02d}")
            save_jsonl(epoch_dir / "shuffled_data.jsonl", shuffled)
            batches = [
                shuffled[i : i + self.cfg.practice.batch_size]
                for i in range(0, len(shuffled), self.cfg.practice.batch_size)
            ]
            for batch_idx, batch in enumerate(batches):
                step_dir = ensure_dir(run_dir / f"step_{step_counter:03d}")
                step_stats = self._run_step(batch, pool, step_dir)
                stats[f"step_{step_counter}"] = {
                    "epoch": epoch,
                    "batch_idx": batch_idx,
                    **step_stats.to_dict(),
                    "num_experiences": len(pool.items),
                }
                save_json(run_dir / "stats.json", stats)
                step_counter += 1
        final_experience_path = run_dir / "experiences_final.json"
        pool.save(final_experience_path)
        enhanced_agent_path = self._export_enhanced_agent_config(final_experience_path)
        save_json(run_dir / "result.json", {"final_experience_file": str(final_experience_path), "enhanced_agent_config": str(enhanced_agent_path), "stats": stats})
        return final_experience_path

    def _build_judge_llm(self):
        if self.eval_cfg and self.eval_cfg.judge_model and self.eval_cfg.judge_model.model_provider:
            provider = self.eval_cfg.judge_model.model_provider
            return OpenAICompatibleLLM(model=provider.model, api_key=provider.resolve_api_key(), base_url=provider.base_url)
        return self.llm

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
            else:
                raise ValueError(f"Unsupported tool in config: {tool_cfg.name}")
        registry = ToolRegistry(tools)
        system_prompt = self.agent_cfg.system_prompt
        if self.agent_cfg.policy == "agent":
            task_prompt = WEB_SYSTEM_PROMPT if self.domain == "web" else MATH_SYSTEM_PROMPT
            react_prompt = REACT_SYSTEM_PROMPT.format(tool_descriptions=registry.describe())
            system_prompt = (system_prompt + "\n\n" + react_prompt) if system_prompt else (task_prompt + "\n\n" + react_prompt)
        return PolicyRunner(self.llm, mode="agent" if self.agent_cfg.policy == "agent" else "prompt", system_prompt=system_prompt, tools=registry)

    def _run_step(self, batch: list[dict[str, Any]], pool: ExperiencePool, step_dir: Path) -> StepStats:
        pool.save(step_dir / "experiences_in.json")
        formatted_experiences = pool.render()
        grouped_rollouts: list[list[Rollout]] = []
        flat_rows: list[dict[str, Any]] = []
        problem_to_scores: dict[str, list[float]] = {}
        tool_call_counts: list[int] = []
        all_rewards: list[float] = []

        for sample_idx, sample in enumerate(batch):
            prompt = self.prompt_template.format(experiences=formatted_experiences, problem=sample["problem"])
            group: list[Rollout] = []
            for k in range(self.cfg.practice.grpo_n):
                rollout = self.policy.rollout(
                    prompt,
                    sample["problem"],
                    temperature=self.cfg.practice.rollout_temperature,
                    max_tokens=self.cfg.practice.max_response_tokens,
                    max_steps=self.cfg.practice.max_policy_steps,
                )
                rollout.runid = sample_idx * self.cfg.practice.grpo_n + k
                rollout.groundtruth = sample.get("groundtruth")
                verification = self._verify(sample, rollout)
                rollout.reward = verification.reward
                rollout.reasoning = verification.reasoning
                group.append(rollout)
                flat_rows.append(rollout.to_dict())
                problem_to_scores.setdefault(sample["problem"], []).append(verification.reward)
                all_rewards.append(verification.reward)
                tool_call_counts.append(self._count_tool_calls(rollout))
            grouped_rollouts.append(group)
        save_jsonl(step_dir / "rollout.jsonl", flat_rows)

        summaries, critiques, group_updates, batch_updates = self._update_experiences(batch, grouped_rollouts, pool, step_dir)
        save_json(step_dir / "single_rollout_summary.json", summaries)
        save_json(step_dir / "single_query_critique.json", critiques)
        if group_updates is not None:
            save_json(step_dir / "group_update.json", group_updates)
        save_json(step_dir / "batch_update.json", batch_updates)
        pool.apply([Operation.from_dict(op) for op in batch_updates])
        pool.save(step_dir / "experiences.json")

        pass_at_k = sum(max(scores) > 0 for scores in problem_to_scores.values()) / max(len(problem_to_scores), 1)
        avg_tool_calls = sum(tool_call_counts) / max(len(tool_call_counts), 1)
        avg_reward = sum(all_rewards) / max(len(all_rewards), 1)
        return StepStats(avg_reward=avg_reward, pass_at_k=pass_at_k, avg_tool_calls=avg_tool_calls)

    def _update_experiences(self, batch: list[dict[str, Any]], grouped: list[list[Rollout]], pool: ExperiencePool, step_dir: Path):
        if self.domain == "math":
            return self._update_math(batch, grouped, pool, step_dir)
        return self._update_web(batch, grouped, pool, step_dir)

    def _update_math(self, batch: list[dict[str, Any]], grouped: list[list[Rollout]], pool: ExperiencePool, step_dir: Path):
        summaries: dict[str, list[dict[str, Any]]] = {}
        critiques: list[dict[str, Any]] = []
        batch_updates: list[dict[str, Any]] = []
        for sample, group in zip(batch, grouped):
            rewards = [float(r.reward or 0) for r in group]
            if self.cfg.practice.given_ground_truth and not (min(rewards) < max(rewards)):
                continue
            sample_summaries: list[dict[str, Any]] = []
            for rollout in group:
                prompt = (
                    SINGLE_ROLLOUT_SUMMARY_TEMPLATE.format(
                        trajectory=json.dumps(rollout.trajectories[0]["trajectory"], ensure_ascii=False, indent=2),
                        grade=f"This trajectory delivers **{'correct' if rollout.reward else 'wrong'}** answer",
                        answer=sample.get("groundtruth") or "N/A",
                    )
                    if self.cfg.practice.given_ground_truth
                    else SINGLE_ROLLOUT_SUMMARY_NO_GT_TEMPLATE.format(
                        trajectory=json.dumps(rollout.trajectories[0]["trajectory"], ensure_ascii=False, indent=2)
                    )
                )
                resp = self.llm.chat([Message(role="user", content=prompt)], temperature=0.2, max_tokens=self.cfg.practice.max_response_tokens)
                sample_summaries.append({"reward": rollout.reward, "summary": resp.content})
            summaries[sample["problem"]] = sample_summaries
            formatted_trajectories = "\n\n".join(
                f"Trajectory {i+1} (Answer {'correct' if item['reward'] else 'wrong'}):\n{item['summary']}"
                for i, item in enumerate(sample_summaries)
            )
            critique_prompt = (
                SINGLE_QUERY_CRITIQUE_TEMPLATE.format(
                    max_operations=self.cfg.practice.num_experiences_per_query,
                    problem=sample["problem"],
                    trajectories=formatted_trajectories,
                    answer=sample.get("groundtruth") or "N/A",
                    experiences=pool.render(),
                )
                if self.cfg.practice.given_ground_truth
                else SINGLE_QUERY_CRITIQUE_NO_GT_TEMPLATE.format(
                    problem=sample["problem"],
                    trajectories=formatted_trajectories,
                    experiences=pool.render(),
                )
            )
            critique_resp = self.llm.chat([Message(role="user", content=critique_prompt)], temperature=0.2, max_tokens=self.cfg.practice.max_response_tokens)
            ops = extract_json(critique_resp.content)
            if not isinstance(ops, list):
                ops = []
            critiques.append({"problem": sample["problem"], "critique": critique_resp.content, "operations": ops})
            batch_updates.extend(op for op in ops if isinstance(op, dict))
        batch_prompt = BATCH_EXPERIENCE_UPDATE_TEMPLATE.format(
            word_limit=self.cfg.practice.experience_word_limit,
            experiences=pool.render(),
            updates=json.dumps(batch_updates, ensure_ascii=False, indent=2),
        )
        batch_resp = self.llm.chat([Message(role="user", content=batch_prompt)], temperature=0.2, max_tokens=self.cfg.practice.max_response_tokens)
        final_ops = extract_json(batch_resp.content)
        if not isinstance(final_ops, list):
            final_ops = []
        return summaries, critiques, None, [op for op in final_ops if isinstance(op, dict)]

    def _update_web(self, batch: list[dict[str, Any]], grouped: list[list[Rollout]], pool: ExperiencePool, step_dir: Path):
        summaries: dict[str, list[dict[str, Any]]] = {}
        critiques: list[dict[str, Any]] = []
        group_update_records: list[dict[str, Any]] = []
        batch_inputs: list[dict[str, Any]] = []
        for sample, group in zip(batch, grouped):
            rewards = [float(r.reward or 0) for r in group]
            if self.cfg.practice.given_ground_truth and not (min(rewards) < max(rewards)):
                continue
            sample_summaries: list[dict[str, Any]] = []
            for rollout in group:
                up = SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP.format(
                    task=sample["problem"],
                    answer=sample.get("groundtruth") or "[REDACTED]",
                    trajectory=json.dumps(rollout.trajectories[0]["trajectory"], ensure_ascii=False, indent=2),
                )
                resp = self.llm.chat(
                    [Message(role="system", content=SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP), Message(role="user", content=up)],
                    temperature=0.2,
                    max_tokens=self.cfg.practice.max_response_tokens,
                )
                sample_summaries.append({"reward": rollout.reward, "summary": resp.content})
            summaries[sample["problem"]] = sample_summaries
            formatted_attempts = "\n\n".join(
                f"Attempt {i+1} (Answer {'correct' if item['reward'] else 'wrong'}):\n{item['summary']}" for i, item in enumerate(sample_summaries)
            )
            critique_up = SINGLE_QUERY_CRITIQUE_TEMPLATE_UP.format(
                question=sample["problem"],
                answer=sample.get("groundtruth") or "[REDACTED]",
                attempts=formatted_attempts,
            )
            critique_resp = self.llm.chat(
                [Message(role="system", content=SINGLE_QUERY_CRITIQUE_TEMPLATE_SP), Message(role="user", content=critique_up)],
                temperature=0.2,
                max_tokens=self.cfg.practice.max_response_tokens,
            )
            extracted_experiences = self._extract_bullet_experiences(critique_resp.content)
            critiques.append({"problem": sample["problem"], "critique": critique_resp.content, "experiences": extracted_experiences})
            if extracted_experiences:
                group_up = GROUP_EXPERIENCE_UPDATE_TEMPLATE_UP.format(
                    existing_experiences=pool.render(),
                    new_experiences="\n".join(f"- {e}" for e in extracted_experiences),
                )
                group_resp = self.llm.chat(
                    [Message(role="system", content=GROUP_EXPERIENCE_UPDATE_TEMPLATE_SP), Message(role="user", content=group_up)],
                    temperature=0.2,
                    max_tokens=self.cfg.practice.max_response_tokens,
                )
                decisions = extract_json(group_resp.content)
                if not isinstance(decisions, list):
                    decisions = []
                group_update_records.append({"problem": sample["problem"], "decisions": decisions})
                for decision in decisions:
                    if isinstance(decision, dict):
                        batch_inputs.append(decision)
        batch_up = BATCH_EXPERIENCE_UPDATE_TEMPLATE_UP.format(
            existing_experiences=pool.render(),
            batch_updates=json.dumps(batch_inputs, ensure_ascii=False, indent=2),
        )
        batch_resp = self.llm.chat(
            [Message(role="system", content=BATCH_EXPERIENCE_UPDATE_TEMPLATE_SP), Message(role="user", content=batch_up)],
            temperature=0.2,
            max_tokens=self.cfg.practice.max_response_tokens,
        )
        final_ops_raw = extract_json(batch_resp.content)
        if not isinstance(final_ops_raw, list):
            final_ops_raw = []
        normalized: list[dict[str, Any]] = []
        for op in final_ops_raw:
            if not isinstance(op, dict):
                continue
            operation = str(op.get("operation") or "NONE").upper()
            if operation == "ADD":
                normalized.append({"option": "add", "experience": op.get("content")})
            elif operation == "UPDATE":
                normalized.append({"option": "modify", "experience": op.get("content"), "modified_from": op.get("id")})
            elif operation == "DELETE":
                normalized.append({"option": "delete", "delete_id": op.get("id")})
        return summaries, critiques, group_update_records, normalized

    def _verify(self, sample: dict[str, Any], rollout: Rollout) -> VerificationResult:
        payload = {"problem": sample["problem"], "groundtruth": sample.get("groundtruth"), "response": rollout.response}
        if self.cfg.practice.reward == "llm":
            return verify_web_llm(payload, self.judge_llm)
        return self.verify(payload, self.judge_llm)

    def _count_tool_calls(self, rollout: Rollout) -> int:
        steps = rollout.trajectories[0]["trajectory"] if rollout.trajectories else []
        return sum(1 for step in steps if step.get("role") == "tool")

    def _extract_bullet_experiences(self, critique: str) -> list[str]:
        lines = [line.strip() for line in critique.splitlines()]
        items = [line.lstrip("-•* ").strip() for line in lines if line.strip().startswith(("-", "•", "*"))]
        return [item for item in items if item]

    def _load_dataset(self, path: str | Path) -> list[dict[str, Any]]:
        path = Path(path)
        if not path.is_absolute():
            path = self.root / path
        rows = load_jsonl(path)
        dataset: list[dict[str, Any]] = []
        for row in rows:
            problem = row.get("problem") or row.get("question") or row.get("query")
            if not isinstance(problem, str) or not problem.strip():
                raise ValueError("Each dataset row must contain problem/question/query")
            dataset.append({
                "problem": problem,
                "groundtruth": row.get("groundtruth") or row.get("answer"),
                **row,
            })
        return dataset

    def _resolved_config_payload(self) -> dict[str, Any]:
        return {
            "exp_id": self.cfg.exp_id,
            "agent_config": self.cfg.agent_config,
            "evaluation_config": self.cfg.evaluation_config,
            "practice": asdict(self.cfg.practice),
            "data": asdict(self.cfg.data),
        }

    def _export_enhanced_agent_config(self, experience_file: Path) -> Path:
        target = ensure_dir(self.root / "configs" / "agents" / "practice") / f"{self.cfg.exp_id}_agent.yaml"
        payload = {
            "policy": self.agent_cfg.policy,
            "system_prompt": self.agent_cfg.system_prompt,
            "model_provider": asdict(self.agent_cfg.model_provider),
            "tools": [asdict(tool) for tool in self.agent_cfg.tools],
            "experience_file": str(experience_file),
        }
        import yaml
        with target.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
        return target
