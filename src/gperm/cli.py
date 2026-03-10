from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Annotated

import tomlkit
import typer
from rich.console import Console
from rich.table import Table

from gperm import __version__
from gperm.adapters import unique_adapters
from gperm.adapters.base import AdapterContext
from gperm.config import load_config, render_config_for_display, write_sample_config
from gperm.i18n import Translator
from gperm.operations import OperationPlan
from gperm.util import xdg_config_home


env_snapshot = dict(os.environ)
translator = Translator.from_env(env_snapshot)
t = translator.text
console = Console()

app = typer.Typer(
    help=t("app.help"),
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
config_app = typer.Typer(
    help=t("config_app.help"),
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(config_app, name="config")


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"gperm {__version__}")
        raise typer.Exit()


ProjectOption = Annotated[
    Path | None,
    typer.Option("--project", help=t("project.help")),
]
ConfigOption = Annotated[
    Path | None,
    typer.Option("--config", help=t("config.help")),
]
AgentOption = Annotated[
    list[str] | None,
    typer.Option("--agent", "-a", help=t("agent.help")),
]
LevelOption = Annotated[
    str,
    typer.Option("--level", help=t("level.help"), case_sensitive=False, show_default=True),
]
ProfileOption = Annotated[
    str | None,
    typer.Option("--profile", help=t("profile.help")),
]
CommandOption = Annotated[
    str | None,
    typer.Option("--command", help=t("command.help")),
]


def _as_toml(payload: dict[str, object]) -> str:
    def sanitize(value):
        if value is None:
            return ""
        if isinstance(value, dict):
            return {key: sanitize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    doc = tomlkit.document()
    doc["config"] = tomlkit.item(sanitize(payload))
    return tomlkit.dumps(doc)


def _resolve_runtime(project: Path | None, config_path: Path | None) -> tuple[dict[str, str], object, AdapterContext]:
    env = dict(os.environ)
    project_root = (project or Path.cwd()).resolve()
    explicit = config_path.resolve() if config_path else None
    loaded = load_config(project_root=project_root, env=env, explicit_config=explicit)
    context = AdapterContext(
        env=env,
        project_root=project_root,
        user_gperm_dir=loaded.user_config_dir,
        project_gperm_dir=loaded.project_config_dir,
    )
    return env, loaded, context


def _print_sources(loaded: object) -> None:
    table = Table(title=t("config.active_sources"))
    table.add_column("Kind")
    table.add_column("Path")
    for source in loaded.config.sources:
        table.add_row(source.label, str(source.path) if source.path else "-")
    console.print(table)


def _selected_adapters(loaded: object, requested_agents: list[str] | None):
    if requested_agents:
        return unique_adapters(requested_agents)
    return unique_adapters(loaded.config.enabled_agents())


def _collect_operations(
    *,
    loaded: object,
    context: AdapterContext,
    requested_agents: list[str] | None,
    level: str,
    profile_override: str | None,
) -> tuple[list[OperationPlan], list[str], dict[str, str], bool]:
    include_global = level in {"global", "all"}
    include_project = level in {"project", "all"}
    warnings: list[str] = []
    resolved_profiles: dict[str, str] = {}
    ignored = include_project and loaded.config.is_ignored(context.project_root, context.env)
    if ignored:
        warnings.append(t("ignored.project"))

    operations: list[OperationPlan] = []
    for adapter in _selected_adapters(loaded, requested_agents):
        if ignored and include_project and not include_global:
            continue

        if profile_override:
            if profile_override not in loaded.config.profiles:
                raise typer.BadParameter(f"Unknown profile: {profile_override}")
            profile = loaded.config.profiles[profile_override]
        else:
            profile = loaded.config.resolve_profile(adapter.metadata.key, context.project_root, context.env)

        resolved_profiles[adapter.metadata.key] = profile.name
        ops, adapter_warnings = adapter.build_operations(
            profile,
            context,
            include_global=include_global,
            include_project=include_project and not ignored,
        )
        operations.extend(ops)
        warnings.extend(f"{adapter.metadata.display_name}: {warning}" for warning in adapter_warnings)

    return operations, warnings, resolved_profiles, ignored


def _status_rows(operations: list[OperationPlan]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for operation in operations:
        rows.append(
            {
                "agent": operation.agent,
                "scope": operation.scope,
                "status": t("status.drift") if operation.changed() else t("status.match"),
                "path": str(operation.path),
                "label": operation.label,
            }
        )
    return rows


def _print_status_table(rows: list[dict[str, str]], title: str) -> None:
    table = Table(title=title)
    table.add_column("Agent")
    table.add_column("Scope")
    table.add_column("Status")
    table.add_column("Path")
    for row in rows:
        table.add_row(row["agent"], row["scope"], row["status"], row["path"])
    console.print(table)


def _print_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    table = Table(title=t("warn.header"))
    table.add_column("Message")
    for warning in warnings:
        table.add_row(warning)
    console.print(table)


def _validated_level(level: str) -> str:
    normalized = level.lower()
    if normalized not in {"global", "project", "all"}:
        raise typer.BadParameter("Level must be one of: global, project, all.")
    return normalized


def _validated_format(output_format: str) -> str:
    normalized = output_format.lower()
    if normalized not in {"table", "json"}:
        raise typer.BadParameter("Format must be one of: table, json.")
    return normalized


def _profile_for(adapter, loaded, context: AdapterContext, profile_name: str | None):
    if profile_name:
        if profile_name not in loaded.config.profiles:
            raise typer.BadParameter(f"Unknown profile: {profile_name}")
        return loaded.config.profiles[profile_name]
    return loaded.config.resolve_profile(adapter.metadata.key, context.project_root, context.env)


@app.callback()
def root_callback(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help=t("version.help")),
    ] = None,
) -> None:
    _ = version


@config_app.command("show", help=t("config.show.help"))
def config_show(
    project: ProjectOption = None,
    config_path: ConfigOption = None,
    output_format: Annotated[str, typer.Option("--format", help=t("format.help"))] = "table",
) -> None:
    env, loaded, _ = _resolve_runtime(project, config_path)
    payload = render_config_for_display(loaded.config, loaded.project_root, env)
    output_format = _validated_format(output_format)

    if output_format == "json":
        console.print_json(json.dumps(payload, ensure_ascii=False))
        return

    _print_sources(loaded)
    console.print(f"{t('config.project_root')}: {loaded.project_root}")
    console.print(f"{t('config.default_profile')}: {loaded.config.default_profile}")
    console.print(f"{t('config.ignored')}: {payload['ignored']}")
    resolved_table = Table(title=t("config.resolved_profiles"))
    resolved_table.add_column("Agent")
    resolved_table.add_column("Profile")
    for agent, profile_name in payload["resolved_profiles"].items():
        resolved_table.add_row(agent, str(profile_name))
    console.print(resolved_table)


@config_app.command("init", help=t("config.init.help"))
def config_init(
    project: ProjectOption = None,
    project_local: Annotated[bool, typer.Option("--project-local", help="Write ./.gperm/config.toml.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing config file.")] = False,
) -> None:
    env = dict(os.environ)
    project_root = (project or Path.cwd()).resolve()
    target = (project_root / ".gperm" / "config.toml") if project_local else (xdg_config_home(env) / "gperm" / "config.toml")
    try:
        write_sample_config(target, force=force)
    except FileExistsError:
        console.print(t("init.exists"))
        raise typer.Exit(1)
    console.print(f"{t('init.wrote')}: {target}")


@app.command("agents", help=t("agents.help"))
def agents_command() -> None:
    from gperm.adapters import ADAPTERS

    seen: set[str] = set()
    table = Table(title="Supported agents")
    table.add_column("Agent")
    table.add_column("Aliases")
    table.add_column("Global")
    table.add_column("Project")
    table.add_column("Inline")
    table.add_column("Tested")
    table.add_column("Notes")
    for adapter in ADAPTERS.values():
        if adapter.metadata.key in seen:
            continue
        seen.add(adapter.metadata.key)
        notes = "experimental" if adapter.metadata.experimental else ""
        table.add_row(
            adapter.metadata.display_name,
            ", ".join(adapter.metadata.aliases),
            adapter.metadata.global_support,
            adapter.metadata.project_support,
            adapter.metadata.inline_support,
            adapter.metadata.tested_version,
            notes,
        )
    console.print(table)


@app.command("check", help=t("check.help"))
def check_command(
    project: ProjectOption = None,
    config_path: ConfigOption = None,
    agent: AgentOption = None,
    level: LevelOption = "all",
    profile: ProfileOption = None,
    output_format: Annotated[str, typer.Option("--format", help=t("format.help"))] = "table",
) -> None:
    env, loaded, context = _resolve_runtime(project, config_path)
    output_format = _validated_format(output_format)
    operations, warnings, resolved_profiles, ignored = _collect_operations(
        loaded=loaded,
        context=context,
        requested_agents=agent,
        level=_validated_level(level),
        profile_override=profile,
    )
    rows = _status_rows(operations)
    payload = {
        "project_root": str(context.project_root),
        "ignored": ignored,
        "resolved_profiles": resolved_profiles,
        "results": rows,
        "warnings": warnings,
    }

    if output_format == "json":
        console.print_json(json.dumps(payload, ensure_ascii=False))
    else:
        _print_sources(loaded)
        _print_status_table(rows, t("check.summary"))
        _print_warnings(warnings)
        for operation in operations:
            if operation.changed():
                console.print(operation.diff_text())

    if any(operation.changed() for operation in operations):
        raise typer.Exit(1)


@app.command("sync", help=t("sync.help"))
def sync_command(
    project: ProjectOption = None,
    config_path: ConfigOption = None,
    agent: AgentOption = None,
    level: LevelOption = "all",
    profile: ProfileOption = None,
    yes: Annotated[bool, typer.Option("--yes", help=t("yes.help"))] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help=t("dry_run.help"))] = False,
) -> None:
    _, loaded, context = _resolve_runtime(project, config_path)
    operations, warnings, _, ignored = _collect_operations(
        loaded=loaded,
        context=context,
        requested_agents=agent,
        level=_validated_level(level),
        profile_override=profile,
    )
    changed = [operation for operation in operations if operation.changed()]

    _print_sources(loaded)
    if ignored and not changed:
        _print_warnings(warnings)
        return

    if not changed:
        console.print(t("sync.no_changes"))
        _print_warnings(warnings)
        return

    _print_status_table(_status_rows(changed), t("sync.pending_changes"))
    for operation in changed:
        console.print(operation.diff_text())
    _print_warnings(warnings)

    if dry_run:
        return

    if not yes and not typer.confirm(t("sync.confirm")):
        console.print(t("sync.aborted"))
        raise typer.Exit(1)

    for operation in changed:
        operation.apply()
        console.print(f"{t('sync.applied')}: {operation.path}")


@app.command("inline", help=t("inline.help"), context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def inline_command(
    ctx: typer.Context,
    agent_name: Annotated[str, typer.Argument()],
    project: ProjectOption = None,
    config_path: ConfigOption = None,
    profile: ProfileOption = None,
    command: CommandOption = None,
) -> None:
    _, loaded, context = _resolve_runtime(project, config_path)
    adapter = _selected_adapters(loaded, [agent_name])[0]
    selected_profile = _profile_for(adapter, loaded, context, profile)
    inline = adapter.inline_args(selected_profile, context)
    target_command = shlex.split(command or loaded.config.resolve_command(adapter.metadata.key))
    output = shlex.join([*inline.args]) if not ctx.args else shlex.join([*target_command, *inline.args, *ctx.args])
    if not inline.args and not ctx.args:
        console.print(t("inline.no_args"))
    else:
        console.print(output)
    _print_warnings(inline.warnings)


@app.command("exec", help=t("exec.help"), context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def exec_command(
    ctx: typer.Context,
    agent_name: Annotated[str, typer.Argument()],
    project: ProjectOption = None,
    config_path: ConfigOption = None,
    profile: ProfileOption = None,
    command: CommandOption = None,
) -> None:
    _, loaded, context = _resolve_runtime(project, config_path)
    adapter = _selected_adapters(loaded, [agent_name])[0]
    selected_profile = _profile_for(adapter, loaded, context, profile)
    inline = adapter.inline_args(selected_profile, context)
    base_command = shlex.split(command or loaded.config.resolve_command(adapter.metadata.key))
    final_command = [*base_command, *inline.args, *ctx.args]
    console.print(f"{t('exec.running')}: {shlex.join(final_command)}")
    _print_warnings(inline.warnings)
    completed = subprocess.run(final_command, check=False)
    raise typer.Exit(completed.returncode)


def main() -> None:
    app()
