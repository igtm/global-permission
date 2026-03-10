from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from gperm import __version__
from gperm.adapters import get_adapter, unique_adapters
from gperm.adapters.base import AdapterContext
from gperm.config import load_config, render_config_for_display, write_sample_config
from gperm.formats import write_data
from gperm.i18n import Translator
from gperm.importers import build_import_plan, merged_import_config
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


def _run_version(command: str) -> str:
    try:
        parts = shlex.split(command)
        completed = subprocess.run(
            [*parts, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""

    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0].strip() if output else ""


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
    if_missing: Annotated[bool, typer.Option("--if-missing", help="Do nothing when the target config already exists.")] = False,
) -> None:
    env = dict(os.environ)
    project_root = (project or Path.cwd()).resolve()
    target = (project_root / ".gperm" / "config.toml") if project_local else (xdg_config_home(env) / "gperm" / "config.toml")
    if target.exists() and if_missing and not force:
        console.print(f"{t('init.skipped')}: {target}")
        return
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


@app.command("import", help=t("import.help"))
def import_command(
    agent_name: Annotated[str, typer.Argument()],
    source_path: Annotated[Path, typer.Argument()],
    target: Annotated[Path | None, typer.Option("--target", help="Target gperm config path.")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="Profile name to create or replace.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing imported profile with the same name.")] = False,
) -> None:
    env = dict(os.environ)
    normalized = agent_name.lower().replace(" ", "").replace("-", "")
    if normalized not in {"claude", "opencode"}:
        raise typer.BadParameter("Import currently supports only: claude, opencode.")

    resolved_source = source_path.expanduser().resolve()
    if not resolved_source.exists():
        raise typer.BadParameter(f"Source file does not exist: {resolved_source}")

    if normalized == "claude" and resolved_source.suffix != ".json":
        raise typer.BadParameter("Claude import expects a JSON settings file.")
    if normalized == "opencode" and resolved_source.suffix not in {".json", ".jsonc"}:
        raise typer.BadParameter("OpenCode import expects a JSON or JSONC config file.")

    plan = build_import_plan(
        "claude" if normalized == "claude" else "opencode",
        resolved_source,
        env,
        target_path=target,
        profile_name=profile,
    )
    merged = merged_import_config(plan.target_path, plan, replace_existing_profile=force)
    write_data(plan.target_path, "toml", merged)

    table = Table(title=f"{agent_name} import")
    table.add_column(t("doctor.item"))
    table.add_column(t("doctor.details"))
    table.add_row(t("import.source"), str(plan.source_path))
    table.add_row(t("import.target"), str(plan.target_path))
    table.add_row(t("import.scope"), plan.scope)
    table.add_row(t("import.profile"), plan.profile_name)
    console.print(table)
    _print_warnings(plan.warnings)
    console.print(f"{t('import.wrote')}: {plan.target_path}")


@app.command("doctor", help=t("doctor.help"))
def doctor_command(
    project: ProjectOption = None,
    config_path: ConfigOption = None,
    agent: AgentOption = None,
    output_format: Annotated[str, typer.Option("--format", help=t("format.help"))] = "table",
) -> None:
    env, loaded, context = _resolve_runtime(project, config_path)
    output_format = _validated_format(output_format)
    selected = _selected_adapters(loaded, agent)
    operations, warnings, resolved_profiles, ignored = _collect_operations(
        loaded=loaded,
        context=context,
        requested_agents=[adapter.metadata.key for adapter in selected],
        level="all",
        profile_override=None,
    )
    operations_by_agent: dict[str, list[OperationPlan]] = {}
    for operation in operations:
        operations_by_agent.setdefault(operation.agent, []).append(operation)

    failures = 0
    summary_rows: list[dict[str, str]] = []
    config_rows: list[dict[str, str]] = []
    agent_rows: list[dict[str, str]] = []

    active_sources = ", ".join(source.label for source in loaded.config.sources)
    config_rows.append(
        {
            "item": t("doctor.active_sources"),
            "status": t("doctor.ok") if loaded.config.sources else t("doctor.warn"),
            "details": active_sources or t("doctor.using_defaults"),
        }
    )
    config_rows.append(
        {
            "item": str(loaded.user_config_path),
            "status": t("doctor.found") if loaded.user_config_path.exists() else t("doctor.missing"),
            "details": "user config",
        }
    )
    config_rows.append(
        {
            "item": str(loaded.project_config_path),
            "status": t("doctor.found") if loaded.project_config_path.exists() else t("doctor.missing"),
            "details": "project override",
        }
    )
    if ignored:
        config_rows.append(
            {
                "item": t("doctor.project_ignored"),
                "status": t("doctor.warn"),
                "details": str(context.project_root),
            }
        )

    for adapter in selected:
        command = loaded.config.resolve_command(adapter.metadata.key)
        executable = shlex.split(command)[0]
        resolved_binary = shutil.which(executable, path=env.get("PATH"))
        version = _run_version(command) if resolved_binary else ""
        profile_name = resolved_profiles.get(adapter.metadata.key, loaded.config.resolve_profile(adapter.metadata.key, context.project_root, context.env).name)
        adapter_operations = operations_by_agent.get(adapter.metadata.key, [])
        drift_count = sum(1 for operation in adapter_operations if operation.changed())
        missing_paths = [str(operation.path) for operation in adapter_operations if not operation.path.exists()]
        status = t("doctor.ok")
        details: list[str] = [f"{t('doctor.profile')}: {profile_name}", f"{t('doctor.command')}: {command}"]

        if not resolved_binary:
            status = t("doctor.fail")
            failures += 1
            details.append("binary not found on PATH")
        else:
            details.append(resolved_binary)
            if version:
                details.append(version)

        if drift_count:
            if status != t("doctor.fail"):
                status = t("doctor.warn")
            details.append(f"drift={drift_count}")
        if missing_paths:
            if status != t("doctor.fail"):
                status = t("doctor.warn")
            details.append("missing: " + ", ".join(missing_paths))

        for operation in adapter_operations:
            op_status = t("doctor.ok")
            if not operation.path.exists():
                op_status = t("doctor.missing")
            elif operation.changed():
                op_status = t("doctor.warn")
            agent_rows.append(
                {
                    "agent": adapter.metadata.display_name,
                    "item": operation.scope,
                    "status": op_status,
                    "details": str(operation.path),
                }
            )

        summary_rows.append(
            {
                "item": adapter.metadata.display_name,
                "status": status,
                "details": " | ".join(details),
            }
        )

    payload = {
        "project_root": str(context.project_root),
        "ignored": ignored,
        "config": config_rows,
        "summary": summary_rows,
        "agent_paths": agent_rows,
        "warnings": warnings,
        "failures": failures,
    }

    if output_format == "json":
        console.print_json(json.dumps(payload, ensure_ascii=False))
    else:
        console.print(f"\n[bold cyan]gperm doctor[/bold cyan] - {t('doctor.title')}\n")

        config_table = Table(title=t("doctor.config"))
        config_table.add_column(t("doctor.item"))
        config_table.add_column(t("doctor.status"))
        config_table.add_column(t("doctor.details"))
        for row in config_rows:
            config_table.add_row(row["item"], row["status"], row["details"])
        console.print(config_table)

        summary_table = Table(title=t("doctor.summary"))
        summary_table.add_column(t("doctor.item"))
        summary_table.add_column(t("doctor.status"))
        summary_table.add_column(t("doctor.details"))
        for row in summary_rows:
            summary_table.add_row(row["item"], row["status"], row["details"])
        console.print(summary_table)

        paths_table = Table(title=t("doctor.agents"))
        paths_table.add_column("Agent")
        paths_table.add_column(t("doctor.item"))
        paths_table.add_column(t("doctor.status"))
        paths_table.add_column(t("doctor.details"))
        for row in agent_rows:
            paths_table.add_row(row["agent"], row["item"], row["status"], row["details"])
        console.print(paths_table)
        _print_warnings(warnings)
        if failures == 0:
            console.print(t("doctor.no_issues"))

    if failures:
        raise typer.Exit(1)


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
