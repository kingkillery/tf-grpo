from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from .utils import normalize_space, truncate_words


@dataclass(slots=True)
class Operation:
    option: str
    experience: Optional[str] = None
    modified_from: Optional[str] = None
    merged_from: list[str] | None = None
    delete_id: Optional[str] = None
    raw: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Operation":
        option = str(payload.get("option") or payload.get("operation") or "").strip().lower()
        if not option:
            raise ValueError("Operation missing option/operation field")
        return cls(
            option=option,
            experience=payload.get("experience") or payload.get("content"),
            modified_from=payload.get("modified_from") or payload.get("id"),
            merged_from=[str(x) for x in payload.get("merged_from", [])] if payload.get("merged_from") else None,
            delete_id=payload.get("delete_id") or (payload.get("id") if option == "delete" else None),
            raw=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "option": self.option,
            "experience": self.experience,
            "modified_from": self.modified_from,
            "merged_from": self.merged_from or [],
            "delete_id": self.delete_id,
        }


class ExperiencePool:
    def __init__(self, items: dict[str, str] | None = None, *, word_limit: int = 32) -> None:
        self.word_limit = word_limit
        self.items: dict[str, str] = dict(items or {})
        self._next_id = self._infer_next_id()

    def _infer_next_id(self) -> int:
        ids = [int(k[1:]) for k in self.items if len(k) > 1 and k[1:].isdigit()]
        return (max(ids) + 1) if ids else 1

    def render(self) -> str:
        if not self.items:
            return "None"
        return "\n".join(f"[{k}] {v}" for k, v in self.items.items())

    def to_dict(self) -> dict[str, str]:
        return dict(self.items)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self.items, handle, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str | Path, *, word_limit: int = 32) -> "ExperiencePool":
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Experience file must be a JSON object of id -> experience")
        return cls({str(k): str(v) for k, v in payload.items()}, word_limit=word_limit)

    def apply(self, operations: Iterable[Operation]) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        for op in operations:
            option = op.option.lower()
            if option in {"add", "update"}:
                content = self._clean(op.experience or "")
                if not content:
                    applied.append({"option": option, "status": "skipped", "reason": "empty"})
                    continue
                if option == "add":
                    if self._has_duplicate(content):
                        applied.append({"option": option, "status": "skipped", "reason": "duplicate"})
                        continue
                    exp_id = f"G{self._next_id}"
                    self._next_id += 1
                    self.items[exp_id] = content
                    applied.append({"option": option, "status": "applied", "id": exp_id})
                else:
                    target = op.modified_from
                    if not target or target not in self.items:
                        applied.append({"option": option, "status": "skipped", "reason": "missing target", "id": target})
                        continue
                    self.items[target] = content
                    applied.append({"option": option, "status": "applied", "id": target})
            elif option == "modify":
                content = self._clean(op.experience or "")
                target = op.modified_from
                if not target or target not in self.items or not content:
                    applied.append({"option": option, "status": "skipped", "reason": "invalid modify", "id": target})
                    continue
                self.items[target] = content
                applied.append({"option": option, "status": "applied", "id": target})
            elif option == "merge":
                ids = [i for i in (op.merged_from or []) if i in self.items]
                content = self._clean(op.experience or "")
                if len(ids) < 2 or not content:
                    applied.append({"option": option, "status": "skipped", "reason": "invalid merge"})
                    continue
                for i in ids:
                    self.items.pop(i, None)
                exp_id = f"G{self._next_id}"
                self._next_id += 1
                self.items[exp_id] = content
                applied.append({"option": option, "status": "applied", "id": exp_id, "merged_from": ids})
            elif option == "delete":
                target = op.delete_id
                if not target or target not in self.items:
                    applied.append({"option": option, "status": "skipped", "reason": "missing target", "id": target})
                    continue
                self.items.pop(target)
                applied.append({"option": option, "status": "applied", "id": target})
            elif option == "none" or option == "keep":
                applied.append({"option": option, "status": "skipped", "reason": option})
            else:
                applied.append({"option": option, "status": "skipped", "reason": "unsupported"})
        self._reindex_if_needed()
        return applied

    def _reindex_if_needed(self) -> None:
        # Keep stable IDs if they already exist; only ensure next fresh ID is valid.
        self._next_id = self._infer_next_id()

    def _clean(self, text: str) -> str:
        return truncate_words(normalize_space(text), self.word_limit)

    def _has_duplicate(self, content: str) -> bool:
        norm = content.casefold()
        return any(v.casefold() == norm for v in self.items.values())
