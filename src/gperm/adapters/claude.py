from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from gperm.adapters.base import AdapterContext, AdapterMetadata, InlineResult, claude_rule_lists, resolved_directories
from gperm.formats import read_data
from gperm.model import PermissionProfile
from gperm.operations import OperationPlan
from gperm.util import home_dir


def _permission_mode(profile: PermissionProfile) -> str:
    mapping = {
        "default": "default",
        "auto-edit": "acceptEdits",
        "full-auto": "dontAsk",
        "plan": "plan",
    }
    return mapping.get(profile.approval, "default")


class ClaudeAdapter:
    metadata = AdapterMetadata(
        key="claude",
        display_name="Claude Code",
        aliases=("claude",),
        default_command="claude",
        tested_version="2.1.62",
        global_support="native",
        project_support="native",
        inline_support="native",
        docs=(
            "https://code.claude.com/docs/en/settings",
            "https://code.claude.com/docs/en/permissions",
        ),
    )

    def _path(self, context: AdapterContext, *, project: bool) -> Path:
        if project:
            return context.project_root / ".claude" / "settings.json"
        return home_dir(context.env) / ".claude" / "settings.json"

    def _desired_managed(self, profile: PermissionProfile, context: AdapterContext) -> tuple[dict[str, object], list[str]]:
        rules = claude_rule_lists(profile)
        managed = {
            "defaultMode": _permission_mode(profile),
            "additionalDirectories": resolved_directories(profile.include_directories, context),
            "permissions": {
                "allow": rules["allow"],
                "ask": rules["ask"],
                "deny": rules["deny"],
            },
        }
        return managed, list(rules["warnings"])

    def _merge(self, current: dict[str, object], desired: dict[str, object]) -> dict[str, object]:
        merged = deepcopy(current)
        merged["defaultMode"] = desired["defaultMode"]
        merged["additionalDirectories"] = desired["additionalDirectories"]
        merged["permissions"] = desired["permissions"]
        return merged

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
        desired_managed, desired_warnings = self._desired_managed(profile, context)
        warnings.extend(desired_warnings)

        if include_global:
            path = self._path(context, project=False)
            current = dict(read_data(path, "json"))
            managed = {
                "defaultMode": current.get("defaultMode"),
                "additionalDirectories": current.get("additionalDirectories", []),
                "permissions": current.get("permissions", {}),
            }
            operations.append(
                OperationPlan(
                    agent=self.metadata.key,
                    scope="global",
                    path=path,
                    file_format="json",
                    label="Claude global settings",
                    current_full=current,
                    desired_full=self._merge(current, desired_managed),
                    current_managed=managed,
                    desired_managed=desired_managed,
                )
            )

        if include_project:
            path = self._path(context, project=True)
            current = dict(read_data(path, "json"))
            managed = {
                "defaultMode": current.get("defaultMode"),
                "additionalDirectories": current.get("additionalDirectories", []),
                "permissions": current.get("permissions", {}),
            }
            operations.append(
                OperationPlan(
                    agent=self.metadata.key,
                    scope="project",
                    path=path,
                    file_format="json",
                    label="Claude project settings",
                    current_full=current,
                    desired_full=self._merge(current, desired_managed),
                    current_managed=managed,
                    desired_managed=desired_managed,
                )
            )

        return operations, warnings

    def inline_args(self, profile: PermissionProfile, context: AdapterContext) -> InlineResult:
        rules = claude_rule_lists(profile)
        args = ["--permission-mode", _permission_mode(profile)]
        if rules["allow"]:
            args.extend(["--allowedTools", *rules["allow"]])
        deny_rules = rules["deny"]
        if deny_rules:
            args.extend(["--disallowedTools", *deny_rules])
        for directory in resolved_directories(profile.include_directories, context):
            args.extend(["--add-dir", directory])
        warnings = list(rules["warnings"])
        if rules["ask"]:
            warnings.append("Claude inline flags cannot express ask-only rules; they are omitted from inline output.")
        return InlineResult(args=args, warnings=warnings)
