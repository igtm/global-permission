## gperm

`gperm` is a unified permission manager for multiple AI coding agent CLIs.

It keeps permission profiles in one place, applies them to native config files when possible, and falls back to inline CLI flags when a tool does not expose persistent project-level settings.

Japanese README: [README.ja.md](./README.ja.md)

## Features

- Unified permission profiles for `claude`, `geminicli`, `copilot`, `codex`, `opencode`, and `antigravity`
- Global config under `XDG_CONFIG_HOME/gperm/config.toml`
- Project override under `./.gperm/config.toml` with higher precedence
- `gperm config show` displays the active config source chain
- `gperm check` shows drift between desired and native settings
- `gperm sync` updates native settings, interactive by default
- `gperm inline` prints inline flags for agents that support runtime permission flags
- `gperm exec` runs the target CLI with expanded inline flags
- Locale-aware CLI messages: English by default, Japanese when `LANG` / `LC_*` starts with `ja`

## Supported agents

| Agent | Alias | Tested version | Global | Project | Inline | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Code | `claude` | `2.1.62` | Native | Native | Native | Uses `~/.claude/settings.json` and `./.claude/settings.json` |
| Gemini CLI | `gemini`, `geminicli` | `0.31.0` | Native | Native | Native | Generates policy TOML under gperm-managed directories |
| GitHub Copilot CLI | `copilot`, `copilot cli`, `copilot-cli` | `1.0.2` | Native | Partial | Native | Persistent project trust is stored in global config; tool rules are runtime-only |
| Codex CLI | `codex` | `0.112.0` | Native | Native | Native | Project trust is managed through global `projects."<path>"` entries |
| OpenCode | `opencode` | `1.2.24` | Native | Native | None | No documented inline permission flags in `gperm 0.0.1` |
| Antigravity | `antigravity` | `1.107.0` | Experimental | Experimental | None | Inferred from installed settings keys, not vendor docs |

## Native config locations

| Agent | Global config | Project config |
| --- | --- | --- |
| Claude Code | `~/.claude/settings.json` | `./.claude/settings.json` |
| Gemini CLI | `~/.gemini/settings.json` and `~/.gemini/trustedFolders.json` | `./.gemini/settings.json` |
| GitHub Copilot CLI | `~/.copilot/config.json` | No native project config file; `gperm` uses global trust entries and inline flags |
| Codex CLI | `~/.codex/config.toml` | `./.codex/config.toml` |
| OpenCode | `~/.config/opencode/opencode.json` or `.jsonc` | `./opencode.json` |
| Antigravity | `~/.config/Antigravity/User/settings.json` | `./.vscode/settings.json` |

## Install

```bash
uv sync
uv run gperm --help
```

## Commands

```bash
gperm --help
gperm --version
gperm agents
gperm config init
gperm config show
gperm check
gperm sync
gperm inline codex
gperm exec copilot -- -p "review this repo"
```

## Config resolution

Resolution order:

1. Built-in defaults
2. `XDG_CONFIG_HOME/gperm/config.toml`
3. `./.gperm/config.toml`

The project-local `./.gperm/config.toml` wins over the XDG config.

## Example config

```toml
version = 1
default_profile = "balanced"

[profiles.safe]
approval = "plan"
sandbox = "read-only"
trust = false

[profiles.balanced]
approval = "default"
sandbox = "workspace-write"
trust = true
allow_shell = ["git status", "git diff"]
deny_shell = ["git push"]

[agents.codex]
profile = "balanced"
command = "codex"

[project]
profile = "safe"
```

## Notes

- `gperm` updates only permission-related keys and leaves unrelated settings intact.
- JSONC files are parsed correctly, but comments and whitespace may be normalized on write.
- For agents that cannot persist some permission concepts natively, `gperm` reports the gap instead of silently dropping it.
- Gemini sidecar policy files are generated under `~/.config/gperm/generated/` or `./.gperm/generated/`.

## Release automation

Merged PRs into `main` can trigger an automatic release when the PR carries exactly one of these labels:

- `release:patch`
- `release:minor`
- `release:major`

The repository now includes:

- [prepare-release.yml](/home/igtm/tmp/global_permission/.github/workflows/prepare-release.yml)
- [publish-release.yml](/home/igtm/tmp/global_permission/.github/workflows/publish-release.yml)
- [scripts/release.py](/home/igtm/tmp/global_permission/scripts/release.py)

Required GitHub secrets:

- `RELEASE_GITHUB_TOKEN`
- `PYPI_API_TOKEN`

## References

- Claude Code permissions: <https://code.claude.com/docs/en/permissions>
- Claude Code settings: <https://code.claude.com/docs/en/settings>
- Gemini CLI policy engine: <https://geminicli.com/docs/reference/policy-engine/>
- GitHub Copilot CLI config: <https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/configure-copilot-cli>
- OpenCode permissions: <https://opencode.ai/docs/ja/permissions/>
- Codex config basics: <https://developers.openai.com/codex/config-basics>
- Codex config reference: <https://developers.openai.com/codex/config-reference>
