---
name: global-permission
description: Use when working on unified permission management for AI coding agent CLIs, especially with gperm profiles, native config sync, drift checks, inline permission flags, project overrides, or support for claude, gemini, copilot, codex, opencode, and antigravity.
---

# Global Permission

Use this skill when the task is about centralized permission control for coding-agent CLIs.

## Workflow

1. Inspect active config with `gperm config show`.
2. If the task is exploratory, run `gperm check` before changing anything.
3. Prefer `gperm sync --dry-run` first when updating multiple agents.
4. Use `gperm sync` without `--yes` unless the caller explicitly wants non-interactive execution.
5. When a target CLI does not support native project persistence, use `gperm inline` or `gperm exec`.

## Config model

- User config: `XDG_CONFIG_HOME/gperm/config.toml`
- Project override: `./.gperm/config.toml`
- Local override wins over XDG config
- Profiles define approval mode, sandbox mode, trust, shell rules, tool rules, URLs, and include directories
- Agent sections select which profile and command each CLI should use

## Support notes

- Claude, Gemini, Codex, and OpenCode have native global and project config handling.
- Copilot persists global config and project trust, but tool rules are mainly runtime flags.
- Antigravity support is experimental and inferred from installed settings keys.
- Gemini policy rules are generated as TOML sidecar files under gperm-managed directories.

## Safe defaults

- Preserve non-permission settings in target files.
- Treat JSONC as parseable input but expect formatting/comments to be normalized on write.
- Report unsupported permission concepts explicitly instead of silently dropping them.
