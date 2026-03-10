from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from gperm.adapters.base import AdapterContext, AdapterMetadata, InlineResult
from gperm.formats import read_data
from gperm.model import PermissionProfile
from gperm.operations import OperationPlan
from gperm.util import xdg_config_home


class AntigravityAdapter:
    metadata = AdapterMetadata(
        key="antigravity",
        display_name="Antigravity",
        aliases=("antigravity",),
        default_command="antigravity",
        tested_version="1.107.0",
        global_support="experimental",
        project_support="experimental",
        inline_support="none",
        docs=(),
        experimental=True,
    )

    def _path(self, context: AdapterContext, *, project: bool) -> Path:
        if project:
            return context.project_root / ".vscode" / "settings.json"
        return xdg_config_home(context.env) / "Antigravity" / "User" / "settings.json"

    def _managed(self, profile: PermissionProfile) -> tuple[dict[str, object], list[str]]:
        warnings: list[str] = [
            "Antigravity support is inferred from installed settings keys, not vendor documentation.",
        ]
        if profile.include_directories:
            warnings.append("Antigravity does not expose include-directory persistence in gperm 0.0.1.")
        if profile.allow_urls or profile.deny_urls:
            warnings.append("Antigravity URL permission persistence is not implemented in gperm 0.0.1.")
        if profile.approval == "auto-edit":
            warnings.append("Antigravity has no native auto-edit-only setting; gperm maps it conservatively.")

        terminal_auto = {command: True for command in profile.allow_shell}
        terminal_auto.update({command: False for command in profile.deny_shell})
        return {
            "chat.tools.autoApprove": profile.approval == "full-auto",
            "chat.tools.terminal.autoApprove": terminal_auto,
        }, warnings

    def build_operations(
        self,
        profile: PermissionProfile,
        context: AdapterContext,
        *,
        include_global: bool,
        include_project: bool,
    ) -> tuple[list[OperationPlan], list[str]]:
        operations: list[OperationPlan] = []
        managed, warnings = self._managed(profile)

        for project_flag in (False, True):
            if project_flag and not include_project:
                continue
            if not project_flag and not include_global:
                continue
            path = self._path(context, project=project_flag)
            current = dict(read_data(path, "jsonc"))
            desired_full = deepcopy(current)
            desired_full["chat.tools.autoApprove"] = managed["chat.tools.autoApprove"]
            desired_full["chat.tools.terminal.autoApprove"] = managed["chat.tools.terminal.autoApprove"]
            operations.append(
                OperationPlan(
                    agent=self.metadata.key,
                    scope="project" if project_flag else "global",
                    path=path,
                    file_format="jsonc",
                    label=f"Antigravity {'project' if project_flag else 'global'} settings",
                    current_full=current,
                    desired_full=desired_full,
                    current_managed={
                        "chat.tools.autoApprove": current.get("chat.tools.autoApprove"),
                        "chat.tools.terminal.autoApprove": current.get("chat.tools.terminal.autoApprove", {}),
                    },
                    desired_managed=managed,
                )
            )

        return operations, warnings

    def inline_args(self, profile: PermissionProfile, context: AdapterContext) -> InlineResult:
        return InlineResult(args=[], warnings=["Antigravity does not expose documented inline permission flags in gperm 0.0.1."])
