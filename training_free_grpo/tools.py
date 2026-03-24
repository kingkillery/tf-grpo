from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import requests


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    def call(self, arguments: dict[str, Any]) -> str:
        raise NotImplementedError

    def describe(self) -> str:
        return f"- {self.name}: {self.description}"


class PythonExecTool(Tool):
    name = "python_exec"
    description = "Execute complete Python code. Arguments: {'code': '<python script>'}. Returns JSON with stdout, stderr, returncode, timed_out."

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    def call(self, arguments: dict[str, Any]) -> str:
        code = arguments.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("python_exec requires a non-empty 'code' argument")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tool.py"
            path.write_text(code, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [sys.executable, str(path)],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
                out = {
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "returncode": proc.returncode,
                    "timed_out": False,
                }
            except subprocess.TimeoutExpired as exc:
                out = {
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "",
                    "returncode": None,
                    "timed_out": True,
                }
        return json.dumps(out, ensure_ascii=False)


class HttpGetTool(Tool):
    name = "get_content"
    description = "Fetch URL content. Arguments: {'url': '<https://...>', 'max_chars': 8000}. Returns plain text."

    def __init__(self, timeout_seconds: float = 20.0, default_max_chars: int = 8000) -> None:
        self.timeout_seconds = timeout_seconds
        self.default_max_chars = default_max_chars

    def call(self, arguments: dict[str, Any]) -> str:
        url = arguments.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise ValueError("get_content requires a valid 'url'")
        max_chars = int(arguments.get("max_chars") or self.default_max_chars)
        resp = requests.get(url, headers={"User-Agent": "training-free-grpo-repro/0.2"}, timeout=self.timeout_seconds)
        resp.raise_for_status()
        text = resp.text
        if "html" in resp.headers.get("Content-Type", "").lower():
            import re
            text = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
        return text[:max_chars]


class SerpApiSearchTool(Tool):
    name = "google_search"
    description = "Search the web via SerpAPI. Arguments: {'query': '<search string>', 'num_results': 5}. Requires SERPAPI_API_KEY."

    def __init__(self, api_key: Optional[str] = None, default_num_results: int = 5, timeout_seconds: float = 20.0) -> None:
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY")
        self.default_num_results = default_num_results
        self.timeout_seconds = timeout_seconds

    def call(self, arguments: dict[str, Any]) -> str:
        if not self.api_key:
            raise RuntimeError("SERPAPI_API_KEY is not set")
        query = arguments.get("query") or arguments.get("q")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("google_search requires a non-empty 'query'")
        n = int(arguments.get("num_results") or self.default_num_results)
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google", "q": query, "num": n, "api_key": self.api_key},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for item in (data.get("organic_results") or [])[:n]:
            items.append({"title": item.get("title"), "link": item.get("link"), "snippet": item.get("snippet")})
        return json.dumps(items, ensure_ascii=False)


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self.tools = {tool.name: tool for tool in (tools or [])}

    def describe(self) -> str:
        if not self.tools:
            return "- no tools registered"
        return "\n".join(tool.describe() for tool in self.tools.values())

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self.tools:
            raise KeyError(f"Unknown tool: {name}")
        return self.tools[name].call(arguments)
