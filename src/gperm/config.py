from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gperm.model import AgentConfig, ConfigSource, GPermConfig, KNOWN_AGENTS, PermissionProfile, ProjectRule, ProjectSettings
from gperm.sample import DEFAULT_CONFIG_TOML
from gperm.util import deep_merge, normalize_agent_name, xdg_config_home


DEFAULT_CONFIG_DATA: dict[str, object] = tomllib.loads(DEFAULT_CONFIG_TOML)


@dataclass(slots=True)
class ConfigLoadResult:
    config: GPermConfig
    project_root: Path
    user_config_path: Path
    project_config_path: Path
    user_config_dir: Path
    project_config_dir: Path


def default_user_config_path(env: dict[str, str]) -> Path:
    return xdg_config_home(env) / "gperm" / "config.toml"


def default_project_config_path(project_root: Path) -> Path:
    return project_root / ".gperm" / "config.toml"


def _load_toml(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _build_config(data: dict[str, Any], sources: list[ConfigSource]) -> GPermConfig:
    profiles_source = dict(data.get("profiles", {}))
    profiles = {
        str(name): PermissionProfile.from_dict(str(name), dict(value))
        for name, value in profiles_source.items()
    }

    if not profiles:
        profiles = {
            str(name): PermissionProfile.from_dict(str(name), dict(value))
            for name, value in dict(DEFAULT_CONFIG_DATA["profiles"]).items()
        }

    agents_source = dict(data.get("agents", {}))
    agents = {
        normalize_agent_name(str(name)): AgentConfig.from_dict(str(name), dict(value))
        for name, value in agents_source.items()
    }
    for name in KNOWN_AGENTS:
        agents.setdefault(name, AgentConfig(name=name))

    project_rules = [ProjectRule.from_dict(dict(item)) for item in list(data.get("project_rules", []))]
    project = ProjectSettings.from_dict(dict(data.get("project", {})))

    return GPermConfig(
        version=int(data.get("version", 1)),
        default_profile=str(data.get("default_profile", "balanced")),
        ignored_projects=[str(item) for item in data.get("ignored_projects", [])],
        profiles=profiles,
        agents=agents,
        project_rules=project_rules,
        project=project,
        sources=sources,
    )


def load_config(
    *,
    project_root: Path,
    env: dict[str, str],
    explicit_config: Path | None = None,
) -> ConfigLoadResult:
    user_path = default_user_config_path(env)
    project_path = default_project_config_path(project_root)

    if explicit_config is not None:
        merged = deep_merge(DEFAULT_CONFIG_DATA, _load_toml(explicit_config))
        config = _build_config(merged, [ConfigSource(label="explicit config", path=explicit_config)])
        return ConfigLoadResult(
            config=config,
            project_root=project_root,
            user_config_path=explicit_config,
            project_config_path=project_path,
            user_config_dir=explicit_config.parent,
            project_config_dir=project_path.parent,
        )

    merged: object = DEFAULT_CONFIG_DATA
    sources: list[ConfigSource] = [ConfigSource(label="built-in defaults", path=None)]

    if user_path.exists():
        merged = deep_merge(merged, _load_toml(user_path))
        sources = [ConfigSource(label="user config", path=user_path)]

    if project_path.exists():
        merged = deep_merge(merged, _load_toml(project_path))
        sources.append(ConfigSource(label="project override", path=project_path))

    config = _build_config(dict(merged), sources)
    return ConfigLoadResult(
        config=config,
        project_root=project_root,
        user_config_path=user_path,
        project_config_path=project_path,
        user_config_dir=user_path.parent,
        project_config_dir=project_path.parent,
    )


def render_config_for_display(config: GPermConfig, project_root: Path, env: dict[str, str]) -> dict[str, object]:
    resolved_profiles = {
        agent: config.resolve_profile_name(agent, project_root, env)
        for agent in config.enabled_agents()
    }
    payload = config.to_dict()
    payload["resolved_profiles"] = resolved_profiles
    payload["ignored"] = config.is_ignored(project_root, env)
    payload["project_root"] = str(project_root)
    payload["sources"] = [
        {"label": source.label, "path": str(source.path) if source.path else None}
        for source in config.sources
    ]
    return payload


def write_sample_config(path: Path, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
