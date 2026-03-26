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


def verify_market_pnl(sample: dict[str, Any], llm: ChatLLM | None = None) -> VerificationResult:
    del llm

    payload = extract_json(str(sample.get("response", "")))
    if not isinstance(payload, dict):
        return VerificationResult(reward=0.0, reasoning="response was not valid JSON")

    recommendation = str(payload.get("recommendation") or "").strip().upper()
    if recommendation not in {"LONG_YES", "LONG_NO", "HOLD"}:
        return VerificationResult(reward=0.0, reasoning="missing or invalid recommendation")

    try:
        yes_price = float(sample.get("yes_price"))
    except (TypeError, ValueError):
        return VerificationResult(reward=0.0, reasoning="sample missing yes_price")

    outcome_raw = str(sample.get("groundtruth") or sample.get("answer") or "").strip().upper()
    if outcome_raw not in {"YES", "NO"}:
        return VerificationResult(reward=0.0, reasoning="sample missing YES/NO groundtruth")

    outcome_yes = 1.0 if outcome_raw == "YES" else 0.0
    size_value = payload.get("position_size", 0.0)
    try:
        position_size = float(size_value)
    except (TypeError, ValueError):
        position_size = 0.0
    position_size = max(0.0, min(0.25, position_size))

    if recommendation == "HOLD":
        reward = 0.0
        reasoning = "hold recommendation yields zero realized edge reward"
    else:
        directional_edge = (outcome_yes - yes_price) if recommendation == "LONG_YES" else (yes_price - outcome_yes)
        size_bonus = 0.1 * (position_size / 0.25) if directional_edge > 0 else 0.0
        reward = max(0.0, min(1.0, directional_edge + size_bonus))
        reasoning = (
            f"recommendation={recommendation} yes_price={yes_price:.4f} outcome={outcome_raw} "
            f"edge={directional_edge:.4f} size={position_size:.4f}"
        )

    return VerificationResult(reward=reward, reasoning=reasoning)


def resolve_verify(verify_type: str) -> VerifyFunc:
    verify_type = verify_type.lower()
    if verify_type == "exact":
        return verify_math
    if verify_type in {"llm", "web_llm"}:
        return verify_web_llm
    if verify_type in {"market_pnl", "trading_pnl"}:
        return verify_market_pnl
    raise ValueError(f"Unsupported verify_type: {verify_type}")
