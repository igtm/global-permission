from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from gperm.config import DEFAULT_CONFIG_DATA
from gperm.formats import read_data
from gperm.model import PermissionProfile
from gperm.util import home_dir, xdg_config_home


@dataclass(slots=True)
class ImportPlan:
    agent: str
    source_path: Path
    target_path: Path
    profile_name: str
    profile: PermissionProfile
    scope: str
    warnings: list[str]


def _approval_from_claude(mode: str) -> str:
    return {
        "acceptEdits": "auto-edit",
        "bypassPermissions": "full-auto",
        "dontAsk": "full-auto",
        "plan": "plan",
        "default": "default",
    }.get(mode, "default")


def _profile_from_claude(path: Path) -> tuple[PermissionProfile, list[str]]:
    data = dict(read_data(path, "json"))
    warnings: list[str] = []
    profile = PermissionProfile(
        name="",
        approval=_approval_from_claude(str(data.get("defaultMode", "default"))),
        sandbox="workspace-write",
        include_directories=[str(item) for item in data.get("additionalDirectories", [])],
    )
    permissions = dict(data.get("permissions", {}))
    tool_map = {
        "Read": "read",
        "Edit": "edit",
        "Write": "write",
        "WebFetch": "webfetch",
        "Bash": "shell",
    }

    for decision, attribute_tools, attribute_shell in (
        ("allow", "allow_tools", "allow_shell"),
        ("deny", "deny_tools", "deny_shell"),
        ("ask", "ask_tools", "ask_shell"),
    ):
        for item in permissions.get(decision, []):
            text = str(item)
            if text.startswith("Bash(") and text.endswith(")"):
                getattr(profile, attribute_shell).append(text[5:-1])
                continue
            mapped = tool_map.get(text)
            if mapped:
                getattr(profile, attribute_tools).append(mapped)
            else:
                warnings.append(f"Claude rule '{text}' could not be mapped to gperm.")
    return profile, warnings


def _profile_from_opencode(path: Path) -> tuple[PermissionProfile, list[str]]:
    file_format = "jsonc" if path.suffix == ".jsonc" else "json"
    data = dict(read_data(path, file_format))
    permission = dict(data.get("permission", {}))
    warnings: list[str] = []
    profile = PermissionProfile(name="", approval="default", sandbox="workspace-write")

    edit = permission.get("edit")
    if edit == "allow":
        profile.allow_tools.extend(["edit", "write"])
    elif edit == "deny":
        profile.deny_tools.extend(["edit", "write"])
    elif edit == "ask":
        profile.ask_tools.extend(["edit", "write"])

    webfetch = permission.get("webfetch")
    if webfetch == "allow":
        profile.allow_tools.append("webfetch")
    elif webfetch == "deny":
        profile.deny_tools.append("webfetch")
    elif webfetch == "ask":
        profile.ask_tools.append("webfetch")

    external_directory = permission.get("external_directory")
    if external_directory == "allow":
        profile.trust = True
    elif external_directory == "deny":
        profile.trust = False

    bash = permission.get("bash")
    if isinstance(bash, str):
        if bash == "allow":
            profile.allow_tools.append("shell")
        elif bash == "deny":
            profile.deny_tools.append("shell")
        elif bash == "ask":
            profile.ask_tools.append("shell")
    elif isinstance(bash, dict):
        default_value = bash.get("*")
        if default_value == "allow":
            profile.allow_tools.append("shell")
        elif default_value == "deny":
            profile.deny_tools.append("shell")
        elif default_value == "ask":
            profile.ask_tools.append("shell")

        for key, value in bash.items():
            if key == "*":
                continue
            command = str(key).rstrip("*")
            if value == "allow":
                profile.allow_shell.append(command)
            elif value == "deny":
                profile.deny_shell.append(command)
            elif value == "ask":
                profile.ask_shell.append(command)
            else:
                warnings.append(f"OpenCode bash rule '{key}' has unsupported value '{value}'.")
    elif bash is not None:
        warnings.append("OpenCode bash permission could not be mapped to gperm.")

    return profile, warnings


def _is_claude_global(source: Path, env: dict[str, str]) -> bool:
    return source == (home_dir(env) / ".claude" / "settings.json")


def _is_opencode_global(source: Path, env: dict[str, str]) -> bool:
    root = xdg_config_home(env) / "opencode"
    return source in {root / "opencode.json", root / "opencode.jsonc"}


def _infer_project_root(agent: str, source: Path) -> Path | None:
    if agent == "claude" and source.name == "settings.json" and source.parent.name == ".claude":
        return source.parent.parent
    if agent == "opencode" and source.name in {"opencode.json", "opencode.jsonc"}:
        return source.parent
    return None


def infer_target_path(agent: str, source: Path, env: dict[str, str], explicit_target: Path | None) -> tuple[Path, str]:
    if explicit_target is not None:
        scope = "project" if explicit_target.parent.name == ".gperm" else "global"
        return explicit_target, scope

    if agent == "claude" and _is_claude_global(source, env):
        return xdg_config_home(env) / "gperm" / "config.toml", "global"
    if agent == "opencode" and _is_opencode_global(source, env):
        return xdg_config_home(env) / "gperm" / "config.toml", "global"

    project_root = _infer_project_root(agent, source) or Path.cwd().resolve()
    return project_root / ".gperm" / "config.toml", "project"


def build_import_plan(
    agent: str,
    source_path: Path,
    env: dict[str, str],
    *,
    target_path: Path | None = None,
    profile_name: str | None = None,
) -> ImportPlan:
    normalized = agent.lower()
    if normalized == "claude":
        profile, warnings = _profile_from_claude(source_path)
    elif normalized == "opencode":
        profile, warnings = _profile_from_opencode(source_path)
    else:
        raise ValueError(f"Import is not supported for agent '{agent}'.")

    chosen_profile = profile_name or f"imported-{normalized}"
    profile.name = chosen_profile
    target, scope = infer_target_path(normalized, source_path, env, target_path.resolve() if target_path else None)
    return ImportPlan(
        agent=normalized,
        source_path=source_path,
        target_path=target,
        profile_name=chosen_profile,
        profile=profile,
        scope=scope,
        warnings=warnings,
    )


def merged_import_config(
    target_path: Path,
    plan: ImportPlan,
    *,
    replace_existing_profile: bool,
) -> dict[str, object]:
    base = copy.deepcopy(DEFAULT_CONFIG_DATA)
    if target_path.exists():
        existing = dict(read_data(target_path, "toml"))
        base.update(existing)

    profiles = dict(base.get("profiles", {}))
    if plan.profile_name in profiles and not replace_existing_profile:
        raise FileExistsError(f"Profile '{plan.profile_name}' already exists in {target_path}.")
    profiles[plan.profile_name] = plan.profile.to_dict()
    base["profiles"] = profiles

    if plan.scope == "global":
        agents = dict(base.get("agents", {}))
        agent_entry = dict(agents.get(plan.agent, {}))
        agent_entry["enabled"] = True
        agent_entry["profile"] = plan.profile_name
        agents[plan.agent] = agent_entry
        base["agents"] = agents
    else:
        project = dict(base.get("project", {}))
        project_agents = dict(project.get("agents", {}))
        agent_entry = dict(project_agents.get(plan.agent, {}))
        agent_entry["enabled"] = True
        agent_entry["profile"] = plan.profile_name
        project_agents[plan.agent] = agent_entry
        project["agents"] = project_agents
        base["project"] = project

    return base
