from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from gperm.adapters.base import AdapterContext, AdapterMetadata, InlineResult, resolved_directories
from gperm.formats import read_data, write_text
from gperm.model import PermissionProfile
from gperm.operations import OperationPlan
from gperm.util import home_dir


def _settings_path(context: AdapterContext, *, project: bool) -> Path:
    if project:
        return context.project_root / ".gemini" / "settings.json"
    return home_dir(context.env) / ".gemini" / "settings.json"


def _trusted_path(context: AdapterContext) -> Path:
    return home_dir(context.env) / ".gemini" / "trustedFolders.json"


def _approval_mode(profile: PermissionProfile, *, inline: bool) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if profile.approval == "auto-edit":
        return "auto_edit", warnings
    if profile.approval == "plan":
        return "plan", warnings
    if profile.approval == "full-auto":
        if inline:
            return "yolo", warnings
        warnings.append("Gemini persistent settings do not support yolo directly; gperm approximates it with auto_edit plus policy rules.")
        return "auto_edit", warnings
    return "default", warnings


def _sandbox_value(profile: PermissionProfile) -> bool:
    return profile.sandbox != "danger-full-access"


def _generated_policy_path(context: AdapterContext, *, project: bool, profile: PermissionProfile) -> Path:
    root = context.project_gperm_dir if project else context.user_gperm_dir
    return root / "generated" / "gemini" / f"{'project' if project else 'global'}-{profile.name}.toml"


def _policy_rules(profile: PermissionProfile) -> tuple[str, list[str]]:
    lines: list[str] = []
    warnings: list[str] = []
    priority = 300

    def emit(tool_name: str, decision: str, command_prefix: str | None = None) -> None:
        nonlocal priority
        lines.append("[[rule]]")
        lines.append(f'toolName = "{tool_name}"')
        if command_prefix is not None:
            lines.append(f'commandPrefix = "{command_prefix}"')
        lines.append(f'decision = "{decision}"')
        lines.append(f"priority = {priority}")
        lines.append("")
        priority -= 10

    for command in profile.deny_shell:
        emit("run_shell_command", "deny", command)
    for command in profile.ask_shell:
        emit("run_shell_command", "ask_user", command)
    for command in profile.allow_shell:
        emit("run_shell_command", "allow", command)

    tool_map = {
        "edit": "replace",
        "write": "write_file",
    }

    for tool in profile.deny_tools:
        mapped = tool_map.get(tool)
        if mapped:
            emit(mapped, "deny")
        elif tool not in {"shell"}:
            warnings.append(f"Gemini policy engine mapping is not implemented for generic tool '{tool}'.")
    for tool in profile.ask_tools:
        mapped = tool_map.get(tool)
        if mapped:
            emit(mapped, "ask_user")
        elif tool not in {"shell"}:
            warnings.append(f"Gemini policy engine mapping is not implemented for generic tool '{tool}'.")
    for tool in profile.allow_tools:
        mapped = tool_map.get(tool)
        if mapped:
            emit(mapped, "allow")
        elif tool not in {"shell"}:
            warnings.append(f"Gemini policy engine mapping is not implemented for generic tool '{tool}'.")

    if "webfetch" in profile.allow_tools or "webfetch" in profile.deny_tools or "webfetch" in profile.ask_tools:
        warnings.append("Gemini webfetch policy mapping is not implemented by gperm.")
    if "read" in profile.allow_tools or "read" in profile.deny_tools or "read" in profile.ask_tools:
        warnings.append("Gemini read-only tool policy mapping is not implemented by gperm.")

    return "\n".join(lines).rstrip() + ("\n" if lines else ""), warnings


class GeminiAdapter:
    metadata = AdapterMetadata(
        key="geminicli",
        display_name="Gemini CLI",
        aliases=("gemini", "geminicli"),
        default_command="gemini",
        tested_version="0.31.0",
        global_support="native",
        project_support="native",
        inline_support="native",
        docs=(
            "https://geminicli.com/docs/reference/policy-engine/",
            "https://geminicli.com/docs/get-started/configuration/",
        ),
    )

    def _settings_operation(self, path: Path, current: dict[str, object], desired: dict[str, object], scope: str) -> OperationPlan:
        managed = {
            "general": {"defaultApprovalMode": dict(current.get("general", {})).get("defaultApprovalMode")},
            "tools": {"sandbox": dict(current.get("tools", {})).get("sandbox")},
            "context": {"includeDirectories": dict(current.get("context", {})).get("includeDirectories", [])},
            "policyPaths": current.get("policyPaths", []),
        }
        merged = deepcopy(current)
        merged["general"] = dict(merged.get("general", {})) | desired["general"]
        merged["tools"] = dict(merged.get("tools", {})) | desired["tools"]
        merged["context"] = dict(merged.get("context", {})) | desired["context"]
        merged["policyPaths"] = desired["policyPaths"]
        return OperationPlan(
            agent=self.metadata.key,
            scope=scope,
            path=path,
            file_format="json",
            label=f"Gemini {scope} settings",
            current_full=current,
            desired_full=merged,
            current_managed=managed,
            desired_managed=desired,
        )

    def build_operations(
        self,
        profile: PermissionProfile,
        context: AdapterContext,
        *,
        include_global: bool,
        include_project: bool,
    ) -> tuple[list[OperationPlan], list[str]]:
        operations: list[OperationPlan] = []
        warnings: list[str] = []

        for project_flag in (False, True):
            if project_flag and not include_project:
                continue
            if not project_flag and not include_global:
                continue

            approval_mode, mode_warnings = _approval_mode(profile, inline=False)
            warnings.extend(mode_warnings)
            include_dirs = resolved_directories(profile.include_directories, context)
            policy_content, policy_warnings = _policy_rules(profile)
            warnings.extend(policy_warnings)
            policy_paths: list[str] = []
            if policy_content:
                policy_path = _generated_policy_path(context, project=project_flag, profile=profile)
                current_policy = policy_path.read_text(encoding="utf-8") if policy_path.exists() else ""
                operations.append(
                    OperationPlan(
                        agent=self.metadata.key,
                        scope="project" if project_flag else "global",
                        path=policy_path,
                        file_format="text",
                        label=f"Gemini {'project' if project_flag else 'global'} generated policy",
                        current_full=current_policy,
                        desired_full=policy_content,
                        current_managed=current_policy,
                        desired_managed=policy_content,
                    )
                )
                policy_paths = [str(policy_path)]

            desired = {
                "general": {"defaultApprovalMode": approval_mode},
                "tools": {"sandbox": _sandbox_value(profile)},
                "context": {"includeDirectories": include_dirs},
                "policyPaths": policy_paths,
            }
            path = _settings_path(context, project=project_flag)
            current = dict(read_data(path, "json"))
            operations.append(self._settings_operation(path, current, desired, "project" if project_flag else "global"))

        if include_project:
            trusted_path = _trusted_path(context)
            current = dict(read_data(trusted_path, "json"))
            desired_full = deepcopy(current)
            desired_full[str(context.project_root)] = "TRUST_FOLDER" if profile.trust else "DO_NOT_TRUST"
            operations.append(
                OperationPlan(
                    agent=self.metadata.key,
                    scope="project",
                    path=trusted_path,
                    file_format="json",
                    label="Gemini trusted folders",
                    current_full=current,
                    desired_full=desired_full,
                    current_managed={str(context.project_root): current.get(str(context.project_root))},
                    desired_managed={str(context.project_root): desired_full[str(context.project_root)]},
                )
            )

        return operations, warnings

    def inline_args(self, profile: PermissionProfile, context: AdapterContext) -> InlineResult:
        approval_mode, warnings = _approval_mode(profile, inline=True)
        args = ["--approval-mode", approval_mode, f"--sandbox={str(_sandbox_value(profile)).lower()}"]
        for directory in resolved_directories(profile.include_directories, context):
            args.extend(["--include-directories", directory])

        policy_content, policy_warnings = _policy_rules(profile)
        warnings.extend(policy_warnings)
        if policy_content:
            policy_path = _generated_policy_path(context, project=True, profile=profile)
            write_text(policy_path, policy_content)
            args.extend(["--policy", str(policy_path)])
        return InlineResult(args=args, warnings=warnings)
