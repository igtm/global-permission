from __future__ import annotations

from gperm.adapters.antigravity import AntigravityAdapter
from gperm.adapters.base import Adapter
from gperm.adapters.claude import ClaudeAdapter
from gperm.adapters.codex import CodexAdapter
from gperm.adapters.copilot import CopilotAdapter
from gperm.adapters.gemini import GeminiAdapter
from gperm.adapters.opencode import OpenCodeAdapter
from gperm.util import normalize_agent_name


ADAPTERS: dict[str, Adapter] = {}
for adapter in (
    ClaudeAdapter(),
    GeminiAdapter(),
    CopilotAdapter(),
    CodexAdapter(),
    OpenCodeAdapter(),
    AntigravityAdapter(),
):
    ADAPTERS[adapter.metadata.key] = adapter
    for alias in adapter.metadata.aliases:
        ADAPTERS[normalize_agent_name(alias)] = adapter


def get_adapter(name: str) -> Adapter:
    normalized = normalize_agent_name(name)
    if normalized not in ADAPTERS:
        raise KeyError(f"Unsupported agent: {name}")
    return ADAPTERS[normalized]


def unique_adapters(names: list[str]) -> list[Adapter]:
    result: list[Adapter] = []
    seen: set[str] = set()
    for name in names:
        adapter = get_adapter(name)
        if adapter.metadata.key not in seen:
            seen.add(adapter.metadata.key)
            result.append(adapter)
    return result
