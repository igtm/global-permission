from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gperm.cli import app


runner = CliRunner()


def test_config_show_json_reports_project_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    user_config = home / ".config" / "gperm" / "config.toml"
    project_config = project / ".gperm" / "config.toml"
    user_config.parent.mkdir(parents=True)
    project_config.parent.mkdir(parents=True)
    project.mkdir(exist_ok=True)

    user_config.write_text(
        'version = 1\n'
        'default_profile = "balanced"\n'
        '[profiles.safe]\n'
        'approval = "plan"\n'
        'sandbox = "read-only"\n'
        '[profiles.balanced]\n'
        'approval = "default"\n'
        'sandbox = "workspace-write"\n',
        encoding="utf-8",
    )
    project_config.write_text('[project]\nprofile = "safe"\n', encoding="utf-8")

    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}
    result = runner.invoke(app, ["config", "show", "--project", str(project), "--format", "json"], env=env)

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["resolved_profiles"]["claude"] == "safe"
    assert payload["sources"][0]["label"] == "user config"
    assert payload["sources"][1]["label"] == "project override"


def test_sync_dry_run_does_not_write_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}

    result = runner.invoke(
        app,
        ["sync", "--project", str(project), "--agent", "claude", "--level", "global", "--dry-run", "--yes"],
        env=env,
    )

    assert result.exit_code == 0
    assert not (home / ".claude" / "settings.json").exists()


def test_inline_outputs_full_command_when_extra_args_are_present(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}

    result = runner.invoke(
        app,
        ["inline", "codex", "--project", str(project), "--command", "codex", "--", "exec", "fix bug"],
        env=env,
    )

    assert result.exit_code == 0
    assert "codex -a" in result.stdout
    assert "exec" in result.stdout
