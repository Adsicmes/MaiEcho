from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from maiecho_py.internal.config.models import (
    AppConfig,
    PromptConfig,
    RuntimeOverrides,
    deep_merge,
)


def _read_yaml_file(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"YAML 内容必须是对象: {path}")
    return raw


def _candidate_paths(
    explicit: Path | None, package_dir: str, filename: str
) -> list[Path]:
    packaged = Path(str(files(package_dir).joinpath(filename)))
    resource_dir = package_dir.split(".")[-1]
    paths: list[Path] = []
    if explicit is not None:
        paths.append(explicit)
    paths.extend(
        [
            Path.cwd() / filename,
            Path.cwd() / resource_dir / filename,
            Path.cwd() / "maiecho_py" / "src" / "maiecho_py" / resource_dir / filename,
            packaged,
        ]
    )
    return paths


def _first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError("未找到所需的配置文件")


def load_app_config(config_path: Path | None = None) -> AppConfig:
    config_file = _first_existing(
        _candidate_paths(config_path, "maiecho_py.config", "config.yaml")
        + _candidate_paths(config_path, "maiecho_py.config", "config.example.yaml")
    )
    yaml_data = _read_yaml_file(config_file)
    overrides = RuntimeOverrides().model_dump(exclude_none=True)
    merged = deep_merge(yaml_data, overrides)
    return AppConfig.model_validate(merged)


def load_prompt_config(prompt_path: Path | None = None) -> PromptConfig:
    prompt_file = _first_existing(
        _candidate_paths(prompt_path, "maiecho_py.prompts", "prompts.yaml")
    )
    yaml_data = _read_yaml_file(prompt_file)
    return PromptConfig.model_validate(yaml_data)
