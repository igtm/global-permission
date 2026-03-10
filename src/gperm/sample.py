DEFAULT_CONFIG_TOML = """version = 1
default_profile = "balanced"
ignored_projects = []

[profiles.safe]
approval = "plan"
sandbox = "read-only"
trust = false
deny_tools = ["edit", "write", "shell", "webfetch"]

[profiles.balanced]
approval = "default"
sandbox = "workspace-write"
trust = true
allow_shell = ["git status", "git diff", "git show", "ls", "pwd", "cat", "rg"]
deny_shell = ["git push", "rm -rf"]

[profiles.full-auto]
approval = "full-auto"
sandbox = "danger-full-access"
trust = true

[agents.claude]
enabled = true
profile = "balanced"
command = "claude"

[agents.geminicli]
enabled = true
profile = "balanced"
command = "gemini"

[agents.copilot]
enabled = true
profile = "balanced"
command = "copilot"

[agents.codex]
enabled = true
profile = "balanced"
command = "codex"

[agents.opencode]
enabled = true
profile = "balanced"
command = "opencode"

[agents.antigravity]
enabled = true
profile = "balanced"
command = "antigravity"

[[project_rules]]
path = "~/work/secrets"
ignore = true

[[project_rules]]
path = "~/work/release"
profile = "safe"
[project_rules.agents.codex]
profile = "full-auto"
"""
