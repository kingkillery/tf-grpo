from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass(slots=True)
class ModelProviderConfig:
    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    api_key: Optional[str] = None

    def resolve_api_key(self) -> str:
        api_key = self.api_key or os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"API key not found. Set {self.api_key_env} or provide api_key in config.")
        return api_key


@dataclass(slots=True)
class ToolConfig:
    name: str
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentConfig:
    policy: str = "direct"
    system_prompt: Optional[str] = None
    model_provider: ModelProviderConfig = field(default_factory=lambda: ModelProviderConfig(model="gpt-4o-mini"))
    tools: list[ToolConfig] = field(default_factory=list)
    experience_file: Optional[str] = None


@dataclass(slots=True)
class PracticeArgs:
    epochs: int = 3
    batch_size: int = 32
    grpo_n: int = 5
    rollout_concurrency: int = 16
    rollout_temperature: float = 0.7
    inference_temperature: float = 0.3
    task_timeout: float = 3600.0
    do_eval: bool = False
    eval_strategy: str = "epoch"
    restart_step: Optional[int] = None
    agent_objective: str = ""
    learning_objective: str = ""
    num_experiences_per_query: int = 1
    max_policy_steps: int = 8
    max_response_tokens: int = 4096
    max_group_update_ops: int = 4
    experience_word_limit: int = 32
    reward: str = "exact"
    given_ground_truth: bool = True


@dataclass(slots=True)
class PracticeDataArgs:
    practice_dataset_path: str


@dataclass(slots=True)
class JudgeModelConfig:
    model_provider: Optional[ModelProviderConfig] = None


@dataclass(slots=True)
class EvalConfig:
    exp_id: str
    agent_config: str
    dataset_path: str
    pass_k: int = 1
    concurrency: int = 16
    verify_type: str = "exact"
    judge_model: Optional[JudgeModelConfig] = None


@dataclass(slots=True)
class PracticeConfig:
    exp_id: str
    agent_config: str
    evaluation_config: Optional[str]
    practice: PracticeArgs
    data: PracticeDataArgs


class ConfigLoader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def load_agent(self, name_or_path: str) -> AgentConfig:
        payload = self._load_yaml(name_or_path, self.root / "configs" / "agents" / "practice")
        model = ModelProviderConfig(**payload.get("model_provider", {}))
        tools = [ToolConfig(**item) for item in payload.get("tools", [])]
        return AgentConfig(
            policy=payload.get("policy", "direct"),
            system_prompt=payload.get("system_prompt"),
            model_provider=model,
            tools=tools,
            experience_file=payload.get("experience_file"),
        )

    def load_eval(self, name_or_path: str) -> EvalConfig:
        payload = self._load_yaml(name_or_path, self.root / "configs" / "eval")
        judge = None
        if payload.get("judge_model") and payload["judge_model"].get("model_provider"):
            judge = JudgeModelConfig(model_provider=ModelProviderConfig(**payload["judge_model"]["model_provider"]))
        return EvalConfig(
            exp_id=payload["exp_id"],
            agent_config=payload["agent_config"],
            dataset_path=payload["dataset_path"],
            pass_k=int(payload.get("pass_k", 1)),
            concurrency=int(payload.get("concurrency", 16)),
            verify_type=payload.get("verify_type", "exact"),
            judge_model=judge,
        )

    def load_practice(self, name_or_path: str) -> PracticeConfig:
        payload = self._load_yaml(name_or_path, self.root / "configs" / "practice")
        return PracticeConfig(
            exp_id=payload["exp_id"],
            agent_config=payload["agent_config"],
            evaluation_config=payload.get("evaluation_config"),
            practice=PracticeArgs(**payload.get("practice", {})),
            data=PracticeDataArgs(**payload.get("data", {})),
        )

    def _load_yaml(self, name_or_path: str, default_dir: Path) -> dict[str, Any]:
        path = Path(name_or_path)
        candidates: list[Path] = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend([
                path,
                self.root / path,
                default_dir / path,
                self.root / default_dir / path,
                path.with_suffix(".yaml"),
                self.root / path.with_suffix(".yaml"),
                default_dir / (str(path) + ".yaml"),
            ])
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                with candidate.open("r", encoding="utf-8") as handle:
                    payload = yaml.safe_load(handle) or {}
                if not isinstance(payload, dict):
                    raise ValueError(f"Invalid YAML mapping: {candidate}")
                return payload
        raise FileNotFoundError(f"Config not found: {name_or_path}")
