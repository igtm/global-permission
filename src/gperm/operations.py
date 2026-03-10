from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gperm.formats import write_data, write_text


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _pretty(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(_normalize(value), indent=2, ensure_ascii=False, sort_keys=True)


@dataclass(slots=True)
class OperationPlan:
    agent: str
    scope: str
    path: Path
    file_format: str
    label: str
    current_full: Any
    desired_full: Any
    current_managed: Any
    desired_managed: Any
    warnings: list[str] = field(default_factory=list)

    def changed(self) -> bool:
        return _normalize(self.current_managed) != _normalize(self.desired_managed)

    def apply(self) -> None:
        if self.file_format == "text":
            write_text(self.path, str(self.desired_full))
            return
        write_data(self.path, self.file_format, self.desired_full)

    def diff_text(self) -> str:
        before = _pretty(self.current_managed).splitlines()
        after = _pretty(self.desired_managed).splitlines()
        return "\n".join(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"{self.label}:current",
                tofile=f"{self.label}:desired",
                lineterm="",
            )
        )
