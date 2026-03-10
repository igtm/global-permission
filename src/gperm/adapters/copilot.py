from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from gperm.adapters.base import AdapterContext, AdapterMetadata, InlineResult, copilot_permission_patterns, resolved_directories
from gperm.formats import read_data
from gperm.model import PermissionProfile
from gperm.operations import OperationPlan
from gperm.util import home_dir, uniq


class CopilotAdapter:
    metadata = AdapterMetadata(
        key="copilot",
        display_name="GitHub Copilot CLI",
        aliases=("copilot", "copilot-cli", "copilot cli"),
        default_command="copilot",
        tested_version="1.0.2",
        global_support="native",
        project_support="partial",
        inline_support="native",
        docs=(
            "https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/configure-copilot-cli",
        ),
    )

    def _path(self, context: AdapterContext) -> Path:
        return home_dir(context.env) / ".copilot" / "config.json"

    def build_operations(
        self,
        profile: PermissionProfile,
        context: AdapterContext,
        *,
        include_global: bool,
        include_project: bool,
    ) -> tuple[list[OperationPlan], list[str]]:
        warnings: list[str] = []
        if profile.allow_tools or profile.deny_tools or profile.ask_tools or profile.allow_shell or profile.deny_shell or profile.ask_shell:
            warnings.append("Copilot persists folder and URL permissions, but tool-level rules are runtime-only via gperm inline/exec.")

        path = self._path(context)
        current = dict(read_data(path, "json"))
        desired_full = deepcopy(current)
        desired_managed: dict[str, object] = {}
        current_managed: dict[str, object] = {}

        if include_global:
            desired_full["allowed_urls"] = list(profile.allow_urls)
            desired_full["denied_urls"] = list(profile.deny_urls)
            desired_managed["allowed_urls"] = list(profile.allow_urls)
            desired_managed["denied_urls"] = list(profile.deny_urls)
            current_managed["allowed_urls"] = current.get("allowed_urls", [])
            current_managed["denied_urls"] = current.get("denied_urls", [])

        if include_project:
            trusted = [str(item) for item in current.get("trusted_folders", [])]
            target_entries = [str(context.project_root), *resolved_directories(profile.include_directories, context)]
            if profile.trust:
                trusted = uniq([*trusted, *target_entries])
            else:
                trusted = [item for item in trusted if item not in target_entries]
            desired_full["trusted_folders"] = trusted
            desired_managed["trusted_folders"] = [entry for entry in target_entries if entry in trusted]
            current_managed["trusted_folders"] = [entry for entry in target_entries if entry in current.get("trusted_folders", [])]

        if not desired_managed:
            return [], warnings

        return [
            OperationPlan(
                agent=self.metadata.key,
                scope="global/project" if include_global and include_project else ("project" if include_project else "global"),
                path=path,
                file_format="json",
                label="Copilot config",
                current_full=current,
                desired_full=desired_full,
                current_managed=current_managed,
                desired_managed=desired_managed,
            )
        ], warnings

    def inline_args(self, profile: PermissionProfile, context: AdapterContext) -> InlineResult:
        allow_patterns, deny_patterns, warnings = copilot_permission_patterns(profile)
        args: list[str] = []
        for pattern in allow_patterns:
            args.extend(["--allow-tool", pattern])
        for pattern in deny_patterns:
            args.extend(["--deny-tool", pattern])
        for url in profile.allow_urls:
            args.extend(["--allow-url", url])
        for url in profile.deny_urls:
            args.extend(["--deny-url", url])
        if profile.trust:
            args.extend(["--add-dir", str(context.project_root)])
        for directory in resolved_directories(profile.include_directories, context):
            args.extend(["--add-dir", directory])
        if profile.ask_tools or profile.ask_shell:
            warnings.append("Copilot inline flags cannot express ask-only rules; they are omitted from inline output.")
        return InlineResult(args=args, warnings=warnings)
