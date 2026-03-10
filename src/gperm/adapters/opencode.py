from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from gperm.adapters.base import AdapterContext, AdapterMetadata, InlineResult, default_decision, opencode_bash_rules
from gperm.formats import read_data
from gperm.model import PermissionProfile
from gperm.operations import OperationPlan
from gperm.util import xdg_config_home


class OpenCodeAdapter:
    metadata = AdapterMetadata(
        key="opencode",
        display_name="OpenCode",
        aliases=("opencode",),
        default_command="opencode",
        tested_version="1.2.24",
        global_support="native",
        project_support="native",
        inline_support="none",
        docs=(
            "https://opencode.ai/docs/ja/permissions/",
            "https://opencode.ai/docs/ja/configuration/",
        ),
    )

    def _path(self, context: AdapterContext, *, project: bool) -> tuple[Path, str]:
        if project:
            return context.project_root / "opencode.json", "json"
        root = xdg_config_home(context.env) / "opencode"
        jsonc_path = root / "opencode.jsonc"
        if jsonc_path.exists():
            return jsonc_path, "jsonc"
        return root / "opencode.json", "json"

    def _managed(self, profile: PermissionProfile) -> tuple[dict[str, object], list[str]]:
        warnings: list[str] = []
        permission = {
            "edit": default_decision(profile, "edit"),
            "bash": opencode_bash_rules(profile),
            "webfetch": default_decision(profile, "webfetch"),
            "external_directory": "allow" if profile.trust or profile.include_directories else default_decision(profile, "shell"),
        }
        if profile.include_directories:
            warnings.append("OpenCode does not support exact include-directory lists; gperm maps them to external_directory permission.")
        return {"permission": permission}, warnings

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
        managed, managed_warnings = self._managed(profile)
        warnings.extend(managed_warnings)

        for project_flag in (False, True):
            if project_flag and not include_project:
                continue
            if not project_flag and not include_global:
                continue
            path, file_format = self._path(context, project=project_flag)
            current = dict(read_data(path, file_format))
            desired_full = deepcopy(current)
            desired_full["permission"] = managed["permission"]
            operations.append(
                OperationPlan(
                    agent=self.metadata.key,
                    scope="project" if project_flag else "global",
                    path=path,
                    file_format=file_format,
                    label=f"OpenCode {'project' if project_flag else 'global'} config",
                    current_full=current,
                    desired_full=desired_full,
                    current_managed={"permission": current.get("permission", {})},
                    desired_managed=managed,
                )
            )

        return operations, warnings

    def inline_args(self, profile: PermissionProfile, context: AdapterContext) -> InlineResult:
        return InlineResult(args=[], warnings=["OpenCode does not expose documented inline permission flags in gperm 0.0.1."])
