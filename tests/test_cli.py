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


def test_config_init_if_missing_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}

    first = runner.invoke(app, ["config", "init"], env=env)
    second = runner.invoke(app, ["config", "init", "--if-missing"], env=env)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "Skipped" in second.stdout or "スキップ" in second.stdout


def test_doctor_reports_missing_agent_binary(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    user_config = home / ".config" / "gperm" / "config.toml"
    project.mkdir()
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        'version = 1\n'
        'default_profile = "balanced"\n'
        '[profiles.balanced]\n'
        'approval = "default"\n'
        'sandbox = "workspace-write"\n'
        '[agents.codex]\n'
        'command = "definitely-missing-codex"\n',
        encoding="utf-8",
    )

    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "PATH": "/usr/bin:/bin"}
    result = runner.invoke(app, ["doctor", "--project", str(project), "--agent", "codex", "--format", "json"], env=env)

    assert result.exit_code == 1
    assert "binary not found on PATH" in result.stdout


def test_import_claude_creates_project_local_gperm_config(tmp_path: Path) -> None:
    project = tmp_path / "project"
    claude_dir = project / ".claude"
    claude_dir.mkdir(parents=True)
    source = claude_dir / "settings.json"
    source.write_text(
        json.dumps(
            {
                "defaultMode": "acceptEdits",
                "additionalDirectories": ["/tmp/shared"],
                "permissions": {
                    "allow": ["Edit", "Bash(git status)"],
                    "deny": ["Bash(git push)"],
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["import", "claude", str(source)])

    target = project / ".gperm" / "config.toml"
    content = target.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert 'imported-claude' in content
    assert 'profile = "imported-claude"' in content
    assert 'approval = "auto-edit"' in content
    assert 'allow_shell = ["git status"]' in content


def test_import_opencode_global_targets_xdg_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_home = home / ".config"
    opencode_root = config_home / "opencode"
    opencode_root.mkdir(parents=True)
    source = opencode_root / "opencode.jsonc"
    source.write_text(
        json.dumps(
            {
                "permission": {
                    "edit": "allow",
                    "bash": {"*": "ask", "git status*": "allow", "git push*": "deny"},
                    "webfetch": "deny",
                    "external_directory": "allow",
                }
            }
        ),
        encoding="utf-8",
    )

    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(config_home)}
    result = runner.invoke(app, ["import", "opencode", str(source)], env=env)

    target = config_home / "gperm" / "config.toml"
    content = target.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert 'imported-opencode' in content
    assert '[agents.opencode]' in content
    assert 'profile = "imported-opencode"' in content
    assert 'trust = true' in content
