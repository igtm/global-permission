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

ワンライナー:

```bash
curl -sSL https://raw.githubusercontent.com/igtm/global-permission/main/install.sh | bash
```

## よく使うコマンド

```bash
gperm import claude ~/.claude/settings.json
gperm import opencode ~/.config/opencode/opencode.jsonc
gperm doctor
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

## ネイティブ設定の取り込み

Claude / OpenCode のネイティブ設定を gperm config に取り込めます。

```bash
gperm import claude ~/.claude/settings.json
gperm import opencode ~/.config/opencode/opencode.jsonc
```

動作:

- Claude の global config は `~/.config/gperm/config.toml` に取り込みます
- OpenCode の global config は `~/.config/gperm/config.toml` に取り込みます
- project 側の source file は `./.gperm/config.toml` に取り込みます
- profile 名の既定値は `imported-claude` / `imported-opencode` です

## 注意

- `gperm` は権限関連キーだけを書き換え、その他の設定は保持します。
- JSONC は正しく読めますが、書き戻し時に comment や空白は正規化されることがあります。
- 各 CLI が表現できない権限概念は、黙って捨てずに warning として表示します。
- Gemini の sidecar policy は `~/.config/gperm/generated/` または `./.gperm/generated/` に生成されます。
- `install.sh` は `gperm` をインストールし、設定が無ければ初期 config を作り、最後に `gperm doctor` を実行します。

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
