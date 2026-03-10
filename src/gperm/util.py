from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from copy import deepcopy
from fnmatch import fnmatch
from pathlib import Path


AGENT_ALIASES = {
    "claude": "claude",
    "codex": "codex",
    "gemini": "geminicli",
    "geminicli": "geminicli",
    "copilot": "copilot",
    "copilotcli": "copilot",
    "copilot-cli": "copilot",
    "opencode": "opencode",
    "antigravity": "antigravity",
}


def normalize_agent_name(value: str) -> str:
    key = value.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    return AGENT_ALIASES.get(key, value.strip().lower())


def detect_locale(env: Mapping[str, str] | None = None) -> str:
    source = env or os.environ
    for name in ("GPERM_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = source.get(name, "").strip().lower()
        if value.startswith("ja"):
            return "ja"
        if value:
            return "en"
    return "en"


def home_dir(env: Mapping[str, str] | None = None) -> Path:
    source = env or os.environ
    return Path(source.get("HOME", str(Path.home()))).expanduser()


def xdg_config_home(env: Mapping[str, str] | None = None) -> Path:
    source = env or os.environ
    configured = source.get("XDG_CONFIG_HOME")
    if configured:
        return Path(configured).expanduser()
    return home_dir(source) / ".config"


def expand_path(raw: str, *, env: Mapping[str, str] | None = None, base: Path | None = None) -> Path:
    source = env or os.environ
    expanded = os.path.expandvars(raw)
    path = Path(expanded).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return path.resolve()


def deep_merge(base: object, overlay: object) -> object:
    if isinstance(base, Mapping) and isinstance(overlay, Mapping):
        merged: dict[str, object] = {str(key): deepcopy(value) for key, value in base.items()}
        for key, value in overlay.items():
            text_key = str(key)
            if text_key in merged:
                merged[text_key] = deep_merge(merged[text_key], value)
            else:
                merged[text_key] = deepcopy(value)
        return merged
    return deepcopy(overlay)


def uniq(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def path_matches(selector: str, project_root: Path, env: Mapping[str, str] | None = None) -> bool:
    if any(token in selector for token in ("*", "?", "[")):
        expanded = os.path.expandvars(selector)
        pattern = str(Path(expanded).expanduser())
        return fnmatch(str(project_root), pattern)

    expected = expand_path(selector, env=env)
    return project_root == expected or project_root.is_relative_to(expected)


def shell_command_variants(command: str) -> list[str]:
    normalized = command.strip()
    if not normalized:
        return []
    if any(token in normalized for token in ("*", "?", "[")):
        return [normalized]
    return uniq([normalized, f"{normalized}:*"])
