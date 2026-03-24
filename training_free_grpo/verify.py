from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .llm import ChatLLM, Message
from .utils import answers_equivalent, extract_json


@dataclass(slots=True)
class VerificationResult:
    reward: float
    reasoning: str | None = None


VerifyFunc = Callable[[dict[str, Any], ChatLLM | None], VerificationResult]


def verify_math(sample: dict[str, Any], llm: ChatLLM | None = None) -> VerificationResult:
    del llm
    answer = sample.get("groundtruth") or sample.get("answer")
    if answer is None:
        raise ValueError("Math verification requires ground truth.")
    response = sample.get("response", "")
    ok = answers_equivalent(str(response), str(answer))
    return VerificationResult(reward=1.0 if ok else 0.0, reasoning=None)


def verify_web_llm(sample: dict[str, Any], llm: ChatLLM | None = None) -> VerificationResult:
    if llm is None:
        raise ValueError("LLM-based web verification requires a judge llm.")
    answer = sample.get("groundtruth") or sample.get("answer") or "N/A"
    prompt = f"""Evaluate whether the candidate answer correctly answers the web task.
Return JSON with keys: reward (0.0 to 1.0) and reasoning.

Task:
{sample['problem']}

Ground truth:
{answer}

Candidate answer:
{sample.get('response','')}
"""
    resp = llm.chat([Message(role="user", content=prompt)], temperature=0.0, max_tokens=512)
    payload = extract_json(resp.content)
    if not isinstance(payload, dict):
        raise ValueError(f"Judge returned invalid payload: {payload}")
    reward = float(payload.get("reward", 0.0))
    reward = max(0.0, min(1.0, reward))
    return VerificationResult(reward=reward, reasoning=str(payload.get("reasoning") or ""))


def resolve_verify(verify_type: str) -> VerifyFunc:
    verify_type = verify_type.lower()
    if verify_type == "exact":
        return verify_math
    if verify_type in {"llm", "web_llm"}:
        return verify_web_llm
    raise ValueError(f"Unsupported verify_type: {verify_type}")
