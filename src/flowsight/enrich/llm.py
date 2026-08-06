"""LLM interface (decision 04) - advisory enrichment, behind a stubbable seam.

The LLM is non-deterministic, so tests NEVER assert its content - only that
enrichment is correctly keyed, attached, cached, and invalidated. ``StubLLMClient``
returns canned JSON for deterministic tests; ``OpenAICompatibleClient`` talks to
any OpenAI-compatible /chat/completions endpoint (DashScope, OpenAI, local) via
urllib - no extra dependency.

Configure at runtime with env vars:
  FLOWSIGHT_LLM_BASE_URL  (e.g. https://dashscope.aliyuncs.com/compatible-mode/v1)
  FLOWSIGHT_LLM_API_KEY
  FLOWSIGHT_LLM_MODEL     (e.g. qwen-plus)
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def chat_json(self, system: str, user: str) -> dict:
        """Return a parsed JSON object. Raises on unavailable / unrecoverable error."""
        ...


SYSTEM = (
    "你是代码分析助手。只输出一个合法 JSON 对象，不要 markdown 代码块、不要解释。"
    "字段用中文简短填写，缺失填空字符串。"
)


class StubLLMClient:
    """Deterministic stub for tests. Returns canned payloads keyed by node id prefix."""

    def __init__(self, payload: dict | None = None):
        # default canned payload (content is irrelevant to tests; presence is what matters)
        self._payload = payload or {
            "purpose": "stub-purpose",
            "contract": {"inputs": "i", "outputs": "o", "errors": "e", "boundaries": "b"},
            "data_flow_role": "transform",
            "risk": {"category": "cat", "severity": "medium", "description": "d", "avoidance": "a"},
        }
        self.calls: list[tuple[str, str]] = []

    def chat_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        return json.loads(json.dumps(self._payload))  # deep copy


class OpenAICompatibleClient:
    """OpenAI-compatible chat client using only urllib."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat_json(self, system: str, user: str) -> dict:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return _extract_json(content)


def _extract_json(text: str) -> dict:
    """Best-effort: pull a JSON object out of an LLM response."""
    text = text.strip()
    # strip ```json ... ``` fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def from_env() -> LLMClient | None:
    """Build an LLM client from env vars, or None if unconfigured."""
    key = os.environ.get("FLOWSIGHT_LLM_API_KEY")
    if not key:
        return None
    base = os.environ.get("FLOWSIGHT_LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.environ.get("FLOWSIGHT_LLM_MODEL", "qwen-plus")
    return OpenAICompatibleClient(base, key, model)
