from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from gperm.adapters.base import AdapterContext, AdapterMetadata, InlineResult, resolved_directories
from gperm.formats import read_data
from gperm.model import PermissionProfile
from gperm.operations import OperationPlan
from gperm.util import home_dir


def _approval_policy(profile: PermissionProfile) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if profile.approval == "full-auto":
        return "never", warnings
    if profile.approval == "plan":
        return "untrusted", warnings
    if profile.approval == "auto-edit":
        warnings.append("Codex has no auto-edit-only approval policy; gperm maps it to on-request.")
    return "on-request", warnings


class CodexAdapter:
    metadata = AdapterMetadata(
        key="codex",
        display_name="Codex CLI",
        aliases=("codex",),
        default_command="codex",
        tested_version="0.112.0",
        global_support="native",
        project_support="native",
        inline_support="native",
        docs=(
            "https://developers.openai.com/codex/config-basics",
            "https://developers.openai.com/codex/config-reference",
            "https://developers.openai.com/codex/sandbox-and-approvals",
        ),
    )

    def _global_path(self, context: AdapterContext) -> Path:
        return home_dir(context.env) / ".codex" / "config.toml"

    def _project_path(self, context: AdapterContext) -> Path:
        return context.project_root / ".codex" / "config.toml"

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
        warnings.extend(
            warning
            for warning in (
                "Codex does not have native URL allow/deny persistence." if profile.allow_urls or profile.deny_urls else "",
                "Codex does not have native shell/tool allow/deny persistence; gperm sync manages approval and sandbox instead."
                if profile.allow_tools or profile.deny_tools or profile.ask_tools or profile.allow_shell or profile.deny_shell or profile.ask_shell
                else "",
                "Codex does not have persistent include-directory settings; use gperm inline/exec for --add-dir."
                if profile.include_directories
                else "",
            )
            if warning
        )

        approval_policy, policy_warnings = _approval_policy(profile)
        warnings.extend(policy_warnings)

        if include_global or include_project:
            path = self._global_path(context)
            current = dict(read_data(path, "toml"))
            desired_full = deepcopy(current)
            current_managed: dict[str, object] = {}
            desired_managed: dict[str, object] = {}

            if include_global:
                desired_full["approval_policy"] = approval_policy
                desired_full["sandbox_mode"] = profile.sandbox
                current_managed["approval_policy"] = current.get("approval_policy")
                current_managed["sandbox_mode"] = current.get("sandbox_mode")
                desired_managed["approval_policy"] = approval_policy
                desired_managed["sandbox_mode"] = profile.sandbox

            if include_project:
                projects = dict(desired_full.get("projects", {}))
                project_entry = dict(projects.get(str(context.project_root), {}))
                current_projects = dict(current.get("projects", {}))
                current_project_entry = dict(current_projects.get(str(context.project_root), {}))
                current_managed["project_trust"] = current_project_entry.get("trust_level")
                if profile.trust:
                    project_entry["trust_level"] = "trusted"
                    projects[str(context.project_root)] = project_entry
                    desired_managed["project_trust"] = "trusted"
                else:
                    projects.pop(str(context.project_root), None)
                    desired_managed["project_trust"] = None
                desired_full["projects"] = projects

            operations.append(
                OperationPlan(
                    agent=self.metadata.key,
                    scope="global/project" if include_global and include_project else ("project" if include_project else "global"),
                    path=path,
                    file_format="toml",
                    label="Codex global config",
                    current_full=current,
                    desired_full=desired_full,
                    current_managed=current_managed,
                    desired_managed=desired_managed,
                )
            )

        if include_project:
            path = self._project_path(context)
            current = dict(read_data(path, "toml"))
            desired_full = deepcopy(current)
            desired_full["approval_policy"] = approval_policy
            desired_full["sandbox_mode"] = profile.sandbox
            operations.append(
                OperationPlan(
                    agent=self.metadata.key,
                    scope="project",
                    path=path,
                    file_format="toml",
                    label="Codex project config",
                    current_full=current,
                    desired_full=desired_full,
                    current_managed={
                        "approval_policy": current.get("approval_policy"),
                        "sandbox_mode": current.get("sandbox_mode"),
                    },
                    desired_managed={
                        "approval_policy": approval_policy,
                        "sandbox_mode": profile.sandbox,
                    },
                )
            )

        return operations, warnings

    def inline_args(self, profile: PermissionProfile, context: AdapterContext) -> InlineResult:
        approval_policy, warnings = _approval_policy(profile)
        args = ["-a", approval_policy, "-s", profile.sandbox]
        for directory in resolved_directories(profile.include_directories, context):
            args.extend(["--add-dir", directory])
        return InlineResult(args=args, warnings=warnings)
