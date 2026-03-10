from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from gperm.model import PermissionProfile
from gperm.operations import OperationPlan
from gperm.util import expand_path, shell_command_variants, uniq


@dataclass(slots=True)
class AdapterContext:
    env: dict[str, str]
    project_root: Path
    user_gperm_dir: Path
    project_gperm_dir: Path


@dataclass(slots=True)
class InlineResult:
    args: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AdapterMetadata:
    key: str
    display_name: str
    aliases: tuple[str, ...]
    default_command: str
    tested_version: str
    global_support: str
    project_support: str
    inline_support: str
    docs: tuple[str, ...] = ()
    experimental: bool = False


class Adapter(Protocol):
    metadata: AdapterMetadata

    def build_operations(
        self,
        profile: PermissionProfile,
        context: AdapterContext,
        *,
        include_global: bool,
        include_project: bool,
    ) -> tuple[list[OperationPlan], list[str]]: ...

    def inline_args(self, profile: PermissionProfile, context: AdapterContext) -> InlineResult: ...


GENERIC_CLAUDE_TOOLS = {
    "read": "Read",
    "edit": "Edit",
    "write": "Write",
    "shell": "Bash",
    "webfetch": "WebFetch",
}

GENERIC_OPENCODE_TOOLS = {
    "edit": "edit",
    "write": "edit",
    "webfetch": "webfetch",
}

GENERIC_COPILOT_TOOLS = {
    "edit": "write",
    "write": "write",
    "shell": "shell",
}


def resolved_directories(entries: list[str], context: AdapterContext) -> list[str]:
    return [str(expand_path(item, env=context.env, base=context.project_root)) for item in entries]


def default_decision(profile: PermissionProfile, tool: str) -> str:
    if profile.approval == "plan" or profile.sandbox == "read-only":
        return "deny" if tool in {"edit", "write", "shell", "webfetch"} else "ask"
    if tool in profile.deny_tools:
        return "deny"
    if tool in profile.ask_tools:
        return "ask"
    if tool in profile.allow_tools:
        return "allow"
    if profile.approval == "full-auto":
        return "allow"
    if profile.approval == "auto-edit" and tool in {"edit", "write"}:
        return "allow"
    return "ask"


def claude_rule_lists(profile: PermissionProfile) -> dict[str, list[str]]:
    allow: list[str] = []
    ask: list[str] = []
    deny: list[str] = []
    warnings: list[str] = []

    for tool in profile.allow_tools:
        mapped = GENERIC_CLAUDE_TOOLS.get(tool)
        if mapped:
            allow.append(mapped)
        else:
            warnings.append(f"Claude does not have a generic mapping for tool '{tool}'.")
    for tool in profile.ask_tools:
        mapped = GENERIC_CLAUDE_TOOLS.get(tool)
        if mapped:
            ask.append(mapped)
        else:
            warnings.append(f"Claude does not have a generic mapping for tool '{tool}'.")
    for tool in profile.deny_tools:
        mapped = GENERIC_CLAUDE_TOOLS.get(tool)
        if mapped:
            deny.append(mapped)
        else:
            warnings.append(f"Claude does not have a generic mapping for tool '{tool}'.")

    for command in profile.allow_shell:
        allow.extend(f"Bash({variant})" for variant in shell_command_variants(command))
    for command in profile.ask_shell:
        ask.extend(f"Bash({variant})" for variant in shell_command_variants(command))
    for command in profile.deny_shell:
        deny.extend(f"Bash({variant})" for variant in shell_command_variants(command))

    return {"allow": uniq(allow), "ask": uniq(ask), "deny": uniq(deny), "warnings": warnings}


def copilot_permission_patterns(profile: PermissionProfile) -> tuple[list[str], list[str], list[str]]:
    allow: list[str] = []
    deny: list[str] = []
    warnings: list[str] = []
    for tool in profile.allow_tools:
        mapped = GENERIC_COPILOT_TOOLS.get(tool)
        if mapped:
            allow.append(mapped)
        else:
            warnings.append(f"Copilot CLI cannot map generic tool '{tool}' to a native allow/deny pattern.")
    for tool in profile.deny_tools:
        mapped = GENERIC_COPILOT_TOOLS.get(tool)
        if mapped:
            deny.append(mapped)
        else:
            warnings.append(f"Copilot CLI cannot map generic tool '{tool}' to a native allow/deny pattern.")
    for command in profile.allow_shell:
        for variant in shell_command_variants(command):
            allow.append(f"shell({variant})")
    for command in profile.deny_shell:
        for variant in shell_command_variants(command):
            deny.append(f"shell({variant})")
    return uniq(allow), uniq(deny), warnings


def opencode_bash_rules(profile: PermissionProfile) -> str | dict[str, str]:
    if not profile.allow_shell and not profile.ask_shell and not profile.deny_shell:
        return default_decision(profile, "shell")
    rules: dict[str, str] = {"*": default_decision(profile, "shell")}
    for command in profile.allow_shell:
        rules[f"{command.strip()}*"] = "allow"
    for command in profile.ask_shell:
        rules[f"{command.strip()}*"] = "ask"
    for command in profile.deny_shell:
        rules[f"{command.strip()}*"] = "deny"
    return rules
