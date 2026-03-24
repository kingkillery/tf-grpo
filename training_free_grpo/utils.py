from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
BOXED_RE = re.compile(r"\\boxed\{([^{}]+)\}")
ANGLE_ANSWER_RE = re.compile(r"<answer>(.*?)</answer>", re.DOTALL | re.IGNORECASE)


def ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no} of {path}: {exc}") from exc
    return rows


def save_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def save_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate_words(text: str, max_words: int) -> str:
    words = normalize_space(text).split()
    return " ".join(words[:max_words]) if len(words) > max_words else " ".join(words)


def extract_json(text: str) -> Any:
    candidates: list[str] = []
    fence = JSON_FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1).strip())
    candidates.extend(_balanced_candidates(text))
    candidates.append(text.strip())
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(candidate)
            except Exception:
                continue
    raise ValueError(f"Could not parse JSON from: {text[:400]}")


def _balanced_candidates(text: str) -> list[str]:
    out: list[str] = []
    for i, ch in enumerate(text):
        if ch in "[{":
            end = _find_end(text, i)
            if end is not None:
                out.append(text[i:end])
    return out


def _find_end(text: str, start: int) -> int | None:
    stack: list[str] = []
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "[{":
            stack.append(ch)
            continue
        if ch in "]}":
            if not stack:
                return None
            opener = stack.pop()
            if (opener, ch) not in {("[", "]"), ("{", "}")}:
                return None
            if not stack:
                return idx + 1
    return None


def extract_answer(text: str) -> str:
    angle = ANGLE_ANSWER_RE.search(text)
    if angle:
        text = angle.group(1)
    boxed = BOXED_RE.findall(text)
    if boxed:
        return normalize_space(boxed[-1])
    return normalize_space(text)


def answers_equivalent(a: str, b: str) -> bool:
    a = extract_answer(a)
    b = extract_answer(b)
    if normalize_space(a).lower() == normalize_space(b).lower():
        return True
    numeric = _numeric_match(a, b)
    if numeric is not None:
        return numeric
    symbolic = _symbolic_match(a, b)
    if symbolic is not None:
        return symbolic
    return False


def _numeric_match(a: str, b: str) -> bool | None:
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    except Exception:
        return None


def _symbolic_match(a: str, b: str) -> bool | None:
    try:
        import sympy as sp  # type: ignore
        return bool(sp.simplify(sp.sympify(a) - sp.sympify(b)) == 0)
    except Exception:
        return None
