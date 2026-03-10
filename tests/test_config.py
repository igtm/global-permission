from __future__ import annotations

from pathlib import Path

from gperm.config import load_config


def test_load_config_prefers_project_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    user_config = home / ".config" / "gperm" / "config.toml"
    project = tmp_path / "project"
    project_config = project / ".gperm" / "config.toml"
    user_config.parent.mkdir(parents=True)
    project_config.parent.mkdir(parents=True)

    user_config.write_text(
        'version = 1\n'
        'default_profile = "balanced"\n'
        '[profiles.safe]\n'
        'approval = "plan"\n'
        'sandbox = "read-only"\n'
        '[profiles.balanced]\n'
        'approval = "default"\n'
        'sandbox = "workspace-write"\n'
        '[agents.codex]\n'
        'profile = "balanced"\n',
        encoding="utf-8",
    )
    project_config.write_text(
        '[project]\n'
        'profile = "safe"\n',
        encoding="utf-8",
    )

    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}
    loaded = load_config(project_root=project, env=env)

    assert [source.label for source in loaded.config.sources] == ["user config", "project override"]
    assert loaded.config.resolve_profile_name("codex", project, env) == "safe"
