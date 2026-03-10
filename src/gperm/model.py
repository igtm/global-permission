from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from gperm.util import normalize_agent_name, path_matches


KNOWN_AGENTS = (
    "claude",
    "geminicli",
    "copilot",
    "codex",
    "opencode",
    "antigravity",
)


@dataclass(slots=True)
class PermissionProfile:
    name: str
    approval: str = "default"
    sandbox: str = "workspace-write"
    trust: bool = False
    include_directories: list[str] = field(default_factory=list)
    allow_tools: list[str] = field(default_factory=list)
    deny_tools: list[str] = field(default_factory=list)
    ask_tools: list[str] = field(default_factory=list)
    allow_shell: list[str] = field(default_factory=list)
    deny_shell: list[str] = field(default_factory=list)
    ask_shell: list[str] = field(default_factory=list)
    allow_urls: list[str] = field(default_factory=list)
    deny_urls: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, name: str, data: dict[str, object]) -> "PermissionProfile":
        return cls(
            name=name,
            approval=str(data.get("approval", "default")),
            sandbox=str(data.get("sandbox", "workspace-write")),
            trust=bool(data.get("trust", False)),
            include_directories=[str(item) for item in data.get("include_directories", [])],
            allow_tools=[str(item) for item in data.get("allow_tools", [])],
            deny_tools=[str(item) for item in data.get("deny_tools", [])],
            ask_tools=[str(item) for item in data.get("ask_tools", [])],
            allow_shell=[str(item) for item in data.get("allow_shell", [])],
            deny_shell=[str(item) for item in data.get("deny_shell", [])],
            ask_shell=[str(item) for item in data.get("ask_shell", [])],
            allow_urls=[str(item) for item in data.get("allow_urls", [])],
            deny_urls=[str(item) for item in data.get("deny_urls", [])],
            notes=str(data.get("notes", "")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "approval": self.approval,
            "sandbox": self.sandbox,
            "trust": self.trust,
            "include_directories": self.include_directories,
            "allow_tools": self.allow_tools,
            "deny_tools": self.deny_tools,
            "ask_tools": self.ask_tools,
            "allow_shell": self.allow_shell,
            "deny_shell": self.deny_shell,
            "ask_shell": self.ask_shell,
            "allow_urls": self.allow_urls,
            "deny_urls": self.deny_urls,
            "notes": self.notes,
        }


@dataclass(slots=True)
class AgentConfig:
    name: str
    enabled: bool = True
    profile: str | None = None
    command: str | None = None

    @classmethod
    def from_dict(cls, name: str, data: dict[str, object]) -> "AgentConfig":
        return cls(
            name=normalize_agent_name(name),
            enabled=bool(data.get("enabled", True)),
            profile=str(data["profile"]) if data.get("profile") else None,
            command=str(data["command"]) if data.get("command") else None,
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"enabled": self.enabled}
        if self.profile is not None:
            result["profile"] = self.profile
        if self.command is not None:
            result["command"] = self.command
        return result


@dataclass(slots=True)
class ProjectRule:
    path: str
    ignore: bool = False
    profile: str | None = None
    agents: dict[str, AgentConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ProjectRule":
        agents = {
            normalize_agent_name(name): AgentConfig.from_dict(name, value)
            for name, value in dict(data.get("agents", {})).items()
        }
        return cls(
            path=str(data["path"]),
            ignore=bool(data.get("ignore", False)),
            profile=str(data["profile"]) if data.get("profile") else None,
            agents=agents,
        )

    def matches(self, project_root: Path, env: dict[str, str]) -> bool:
        return path_matches(self.path, project_root, env)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"path": self.path}
        if self.ignore:
            result["ignore"] = True
        if self.profile is not None:
            result["profile"] = self.profile
        if self.agents:
            result["agents"] = {name: value.to_dict() for name, value in self.agents.items()}
        return result


@dataclass(slots=True)
class ProjectSettings:
    ignore: bool = False
    profile: str | None = None
    agents: dict[str, AgentConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ProjectSettings":
        agents = {
            normalize_agent_name(name): AgentConfig.from_dict(name, value)
            for name, value in dict(data.get("agents", {})).items()
        }
        return cls(
            ignore=bool(data.get("ignore", False)),
            profile=str(data["profile"]) if data.get("profile") else None,
            agents=agents,
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {}
        if self.ignore:
            result["ignore"] = True
        if self.profile is not None:
            result["profile"] = self.profile
        if self.agents:
            result["agents"] = {name: value.to_dict() for name, value in self.agents.items()}
        return result


@dataclass(slots=True)
class ConfigSource:
    label: str
    path: Path | None


@dataclass(slots=True)
class GPermConfig:
    version: int
    default_profile: str
    ignored_projects: list[str]
    profiles: dict[str, PermissionProfile]
    agents: dict[str, AgentConfig]
    project_rules: list[ProjectRule]
    project: ProjectSettings
    sources: list[ConfigSource] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "default_profile": self.default_profile,
            "ignored_projects": self.ignored_projects,
            "profiles": {name: profile.to_dict() for name, profile in self.profiles.items()},
            "agents": {name: agent.to_dict() for name, agent in self.agents.items()},
            "project_rules": [rule.to_dict() for rule in self.project_rules],
            "project": self.project.to_dict(),
        }

    def enabled_agents(self, requested: list[str] | None = None) -> list[str]:
        candidates = requested or list(KNOWN_AGENTS)
        result: list[str] = []
        for item in candidates:
            name = normalize_agent_name(item)
            config = self.agents.get(name)
            if config and not config.enabled:
                continue
            if name in KNOWN_AGENTS and name not in result:
                result.append(name)
        return result

    def is_ignored(self, project_root: Path, env: dict[str, str]) -> bool:
        if self.project.ignore:
            return True
        for selector in self.ignored_projects:
            if path_matches(selector, project_root, env):
                return True
        for rule in self.project_rules:
            if rule.ignore and rule.matches(project_root, env):
                return True
        return False

    def resolve_profile_name(self, agent_name: str, project_root: Path, env: dict[str, str]) -> str:
        name = normalize_agent_name(agent_name)
        if name in self.project.agents and self.project.agents[name].profile:
            return self.project.agents[name].profile or self.default_profile

        for rule in reversed(self.project_rules):
            if rule.matches(project_root, env) and name in rule.agents and rule.agents[name].profile:
                return rule.agents[name].profile or self.default_profile

        if self.project.profile:
            return self.project.profile

        for rule in reversed(self.project_rules):
            if rule.matches(project_root, env) and rule.profile:
                return rule.profile

        if name in self.agents and self.agents[name].profile:
            return self.agents[name].profile or self.default_profile

        return self.default_profile

    def resolve_profile(self, agent_name: str, project_root: Path, env: dict[str, str]) -> PermissionProfile:
        profile_name = self.resolve_profile_name(agent_name, project_root, env)
        if profile_name not in self.profiles:
            raise KeyError(f"Unknown profile: {profile_name}")
        return self.profiles[profile_name]

    def resolve_command(self, agent_name: str) -> str:
        name = normalize_agent_name(agent_name)
        configured = self.agents.get(name)
        if configured and configured.command:
            return configured.command
        defaults = {
            "claude": "claude",
            "geminicli": "gemini",
            "copilot": "copilot",
            "codex": "codex",
            "opencode": "opencode",
            "antigravity": "antigravity",
        }
        return defaults[name]
