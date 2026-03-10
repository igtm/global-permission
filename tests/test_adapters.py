from __future__ import annotations

from pathlib import Path

from gperm.adapters import get_adapter
from gperm.adapters.base import AdapterContext
from gperm.model import PermissionProfile


def make_context(tmp_path: Path) -> AdapterContext:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}
    return AdapterContext(
        env=env,
        project_root=project,
        user_gperm_dir=Path(env["XDG_CONFIG_HOME"]) / "gperm",
        project_gperm_dir=project / ".gperm",
    )


def test_claude_sync_preserves_unrelated_settings(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    settings_path = Path(context.env["HOME"]) / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"AWS_REGION":"ap-northeast-1"}', encoding="utf-8")

    adapter = get_adapter("claude")
    profile = PermissionProfile(name="balanced", allow_shell=["git status"], deny_shell=["git push"])
    operations, warnings = adapter.build_operations(profile, context, include_global=True, include_project=False)

    assert not warnings
    desired = operations[0].desired_full
    assert desired["AWS_REGION"] == "ap-northeast-1"
    assert "permissions" in desired
    assert "Bash(git status)" in desired["permissions"]["allow"]
    assert "Bash(git push)" in desired["permissions"]["deny"]


def test_gemini_builds_generated_policy_and_trust_entry(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    adapter = get_adapter("gemini")
    profile = PermissionProfile(name="balanced", trust=True, allow_shell=["git status"], deny_shell=["git push"])
    operations, warnings = adapter.build_operations(profile, context, include_global=False, include_project=True)

    assert any("Gemini project settings" == operation.label for operation in operations)
    assert any("generated policy" in operation.label for operation in operations)
    trusted = next(operation for operation in operations if operation.label == "Gemini trusted folders")
    assert trusted.desired_managed[str(context.project_root)] == "TRUST_FOLDER"
    assert not any("not implemented" in warning for warning in warnings)


def test_copilot_inline_patterns_include_add_dir(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    adapter = get_adapter("copilot")
    profile = PermissionProfile(name="balanced", trust=True, allow_shell=["git status"], deny_shell=["git push"])
    inline = adapter.inline_args(profile, context)

    assert "--allow-tool" in inline.args
    assert "shell(git status)" in inline.args
    assert "shell(git push)" in inline.args
    assert "--add-dir" in inline.args
    assert str(context.project_root) in inline.args


def test_codex_project_sync_preserves_other_projects(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    config_path = Path(context.env["HOME"]) / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        'model = "gpt-5"\n'
        '[projects."/tmp/other"]\n'
        'trust_level = "trusted"\n',
        encoding="utf-8",
    )

    adapter = get_adapter("codex")
    profile = PermissionProfile(name="balanced", trust=True, sandbox="workspace-write", approval="default")
    operations, _ = adapter.build_operations(profile, context, include_global=False, include_project=True)
    global_op = next(operation for operation in operations if operation.label == "Codex global config")

    assert global_op.desired_full["model"] == "gpt-5"
    assert global_op.desired_full["projects"]["/tmp/other"]["trust_level"] == "trusted"
    assert global_op.desired_full["projects"][str(context.project_root)]["trust_level"] == "trusted"


def test_opencode_preserves_unrelated_settings(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    opencode_root = Path(context.env["XDG_CONFIG_HOME"]) / "opencode"
    config_path = opencode_root / "opencode.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('{"share":"disabled"}', encoding="utf-8")

    adapter = get_adapter("opencode")
    profile = PermissionProfile(name="safe", approval="plan", sandbox="read-only")
    operations, _ = adapter.build_operations(profile, context, include_global=True, include_project=False)
    desired = operations[0].desired_full

    assert desired["share"] == "disabled"
    assert desired["permission"]["edit"] == "deny"
