# gperm

`gperm` は、複数の AI coding agent CLI の権限設定を一元管理して同期するツールです。

1つの profile を元に、各 CLI のネイティブ設定ファイルへ反映し、永続化できないものは inline 引数に展開します。

## 主な機能

- `claude`, `geminicli`, `copilot`, `codex`, `opencode`, `antigravity` に対応
- `XDG_CONFIG_HOME/gperm/config.toml` にユーザー設定
- `./.gperm/config.toml` に project override
- `gperm config show` でどの設定ソースが有効か表示
- `gperm check` で drift を確認
- `gperm sync` で一括更新。デフォルトは対話確認あり
- `gperm inline` で profile を CLI 引数に展開
- `gperm exec` で profile 展開済みの状態で CLI 実行
- 実行環境が日本語ならメッセージも日本語化

## 対応表

| Agent | Alias | 確認バージョン | Global | Project | Inline | 備考 |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Code | `claude` | `2.1.62` | Native | Native | Native | `~/.claude/settings.json`, `./.claude/settings.json` |
| Gemini CLI | `gemini`, `geminicli` | `0.31.0` | Native | Native | Native | policy TOML を gperm 管理ディレクトリに生成 |
| GitHub Copilot CLI | `copilot`, `copilot cli`, `copilot-cli` | `1.0.2` | Native | Partial | Native | project trust は global config、tool rule は runtime 展開中心 |
| Codex CLI | `codex` | `0.112.0` | Native | Native | Native | project trust は global の `projects."<path>"` で管理 |
| OpenCode | `opencode` | `1.2.24` | Native | Native | None | `gperm 0.0.1` では documented な inline flag なし |
| Antigravity | `antigravity` | `1.107.0` | Experimental | Experimental | None | ベンダー docs ではなくインストール済み設定キーから推定 |

## ネイティブ設定ファイル

| Agent | Global | Project |
| --- | --- | --- |
| Claude Code | `~/.claude/settings.json` | `./.claude/settings.json` |
| Gemini CLI | `~/.gemini/settings.json`, `~/.gemini/trustedFolders.json` | `./.gemini/settings.json` |
| GitHub Copilot CLI | `~/.copilot/config.json` | ネイティブな project config なし |
| Codex CLI | `~/.codex/config.toml` | `./.codex/config.toml` |
| OpenCode | `~/.config/opencode/opencode.json` または `.jsonc` | `./opencode.json` |
| Antigravity | `~/.config/Antigravity/User/settings.json` | `./.vscode/settings.json` |

## インストール

```bash
uv sync
uv run gperm --help
```

## よく使うコマンド

```bash
gperm config init
gperm config show
gperm check
gperm sync
gperm inline codex
gperm exec copilot -- -p "review this repo"
```

## 設定の優先順位

1. 組み込みデフォルト
2. `XDG_CONFIG_HOME/gperm/config.toml`
3. `./.gperm/config.toml`

`./.gperm/config.toml` があればそれが優先されます。

## 設定例

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

## 注意

- `gperm` は権限関連キーだけを書き換え、その他の設定は保持します。
- JSONC は正しく読めますが、書き戻し時に comment や空白は正規化されることがあります。
- 各 CLI が表現できない権限概念は、黙って捨てずに warning として表示します。
- Gemini の sidecar policy は `~/.config/gperm/generated/` または `./.gperm/generated/` に生成されます。

## Release 自動化

`main` に merge された PR に次の label がちょうど 1 つ付いていると、自動で release が走るようにしました。

- `release:patch`
- `release:minor`
- `release:major`

含まれるもの:

- [prepare-release.yml](/home/igtm/tmp/global_permission/.github/workflows/prepare-release.yml)
- [publish-release.yml](/home/igtm/tmp/global_permission/.github/workflows/publish-release.yml)
- [scripts/release.py](/home/igtm/tmp/global_permission/scripts/release.py)

必要な GitHub secret:

- `RELEASE_GITHUB_TOKEN`
- `PYPI_API_TOKEN`

smoke test なら、docs だけの小さな PR に release label を 1 つ付ければ一連の pipeline を確認できます。
