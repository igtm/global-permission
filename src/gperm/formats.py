from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import json5
import tomlkit


def read_data(path: Path, file_format: str) -> Any:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    if file_format in {"json", "jsonc"}:
        return json5.loads(text)
    if file_format == "toml":
        return tomllib.loads(text)
    raise ValueError(f"Unsupported file format: {file_format}")


def write_data(path: Path, file_format: str, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if file_format in {"json", "jsonc"}:
        rendered = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    elif file_format == "toml":
        doc = tomlkit.document()
        if isinstance(data, dict):
            for key, value in data.items():
                doc[key] = tomlkit.item(value)
        else:
            raise TypeError("TOML data must be a dictionary")
        rendered = tomlkit.dumps(doc)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")
    path.write_text(rendered, encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
