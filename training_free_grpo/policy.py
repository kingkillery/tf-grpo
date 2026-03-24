from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .llm import ChatLLM, Message
from .tools import ToolRegistry
from .utils import extract_json

REACT_SYSTEM_PROMPT = """You are a tool-using reasoning agent.
Respond with a single JSON object and nothing else.
Valid schemas:
1. Tool call:
{{"thought": "brief reasoning", "action": {{"type": "tool", "name": "tool_name", "arguments": {{}}}}}}
2. Final answer:
{{"thought": "brief reasoning", "action": {{"type": "final", "answer": "final answer"}}}}
Available tools:
{tool_descriptions}
Use exactly one tool at a time. When you have enough information, return the final answer.
"""


@dataclass(slots=True)
class TrajectoryStep:
    role: str
    content: str
    tool_name: Optional[str] = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    observation: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "observation": self.observation,
        }


@dataclass(slots=True)
class Rollout:
    problem: str
    prompt: str
    response: str
    trajectories: list[dict[str, Any]]
    reward: float | None = None
    reasoning: str | None = None
    error: str | None = None
    runid: int | None = None
    groundtruth: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem": self.problem,
            "prompt": self.prompt,
            "response": self.response,
            "trajectories": self.trajectories,
            "reward": self.reward,
            "reasoning": self.reasoning,
            "error": self.error,
            "runid": self.runid,
            "groundtruth": self.groundtruth,
        }


class PolicyRunner:
    def __init__(self, llm: ChatLLM, *, mode: str = "prompt", system_prompt: Optional[str] = None, tools: ToolRegistry | None = None) -> None:
        self.llm = llm
        self.mode = mode
        self.system_prompt = system_prompt
        self.tools = tools or ToolRegistry()

    def rollout(self, prompt: str, problem: str, *, temperature: float = 0.7, max_tokens: int = 4096, max_steps: int = 8) -> Rollout:
        if self.mode == "prompt":
            messages = []
            if self.system_prompt:
                messages.append(Message(role="system", content=self.system_prompt))
            messages.append(Message(role="user", content=prompt))
            resp = self.llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
            traj = [{"trajectory": [{"role": "user", "content": prompt}, {"role": "assistant", "content": resp.content}]}]
            return Rollout(problem=problem, prompt=prompt, response=resp.content, trajectories=traj)
        if self.mode != "agent":
            raise ValueError(f"Unsupported policy mode: {self.mode}")

        system = self.system_prompt or REACT_SYSTEM_PROMPT.format(tool_descriptions=self.tools.describe())
        messages = [Message(role="system", content=system), Message(role="user", content=prompt)]
        trajectory: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        final_answer = ""
        for _ in range(max_steps):
            resp = self.llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
            payload = extract_json(resp.content)
            if not isinstance(payload, dict) or not isinstance(payload.get("action"), dict):
                trajectory.append({"role": "assistant", "content": resp.content})
                final_answer = resp.content
                break
            thought = str(payload.get("thought") or "")
            action = payload["action"]
            kind = str(action.get("type") or "").lower()
            if kind == "final":
                final_answer = str(action.get("answer") or "")
                trajectory.append({"role": "assistant", "content": thought or final_answer})
                break
            if kind != "tool":
                trajectory.append({"role": "assistant", "content": resp.content})
                final_answer = resp.content
                break
            name = str(action.get("name") or "")
            arguments = action.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            try:
                observation = self.tools.call(name, arguments)
            except Exception as exc:
                observation = f"tool_error: {exc}"
            trajectory.append({
                "role": "assistant",
                "content": thought,
                "tool_calls": [{"function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}],
            })
            trajectory.append({"role": "tool", "content": observation, "tool_name": name})
            messages.append(Message(role="assistant", content=json.dumps(payload, ensure_ascii=False)))
            messages.append(Message(role="user", content=f"Observation from tool `{name}`:\n{observation}"))
        if not final_answer:
            resp = self.llm.chat(messages + [Message(role="user", content="Provide your best final answer now.")], temperature=temperature, max_tokens=max_tokens)
            try:
                payload = extract_json(resp.content)
                if isinstance(payload, dict) and isinstance(payload.get("action"), dict) and str(payload["action"].get("type","")) == "final":
                    final_answer = str(payload["action"].get("answer") or "")
                else:
                    final_answer = resp.content
            except Exception:
                final_answer = resp.content
            trajectory.append({"role": "assistant", "content": final_answer})
        return Rollout(problem=problem, prompt=prompt, response=final_answer, trajectories=[{"trajectory": trajectory}])
