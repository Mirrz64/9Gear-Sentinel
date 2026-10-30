"""Load sentinel.yml: parse YAML, fill ${VARS}, validate, and report errors by line."""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError, YAMLError

from sentinel.config.models import CHECK_TYPES, SentinelConfig

Loc = tuple[str | int, ...]

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


@dataclass(frozen=True)
class ConfigIssue:
    file: str
    line: int | None
    path: str
    message: str

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return f"{where} {self.path}: {self.message}" if self.path else f"{where} {self.message}"


class ConfigError(Exception):
    def __init__(self, issues: list[ConfigIssue]) -> None:
        self.issues = issues
        super().__init__("\n".join(str(issue) for issue in issues))


def load_config(
    path: str | Path,
    *,
    require_env: bool = True,
    environ: Mapping[str, str] | None = None,
) -> SentinelConfig:
    """Load and validate a config file.

    ``require_env=False`` leaves unresolved ``${VARS}`` in place, which lets
    ``sentinel validate --skip-env`` check structure in CI without secrets.
    ``environ`` replaces os.environ, mainly for tests.
    """
    path = Path(path)
    file_label = str(path)
    if not path.is_file():
        raise ConfigError(
            [ConfigIssue(file_label, None, "", "file not found; run `sentinel init` to create one")]
        )

    data = _parse_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError(
            [ConfigIssue(file_label, 1, "", "the top level must be a mapping of key: value pairs")]
        )

    env = _environment(path.parent, environ)
    issues: list[ConfigIssue] = []
    _substitute_env(data, data, (), env, require_env, file_label, issues)
    if issues:
        raise ConfigError(issues)

    try:
        config = SentinelConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(
            [_issue_from_pydantic(error, data, file_label) for error in exc.errors()]
        ) from None

    issues = _cross_reference(config, data, file_label)
    if issues:
        raise ConfigError(issues)
    return config


# --- parsing --------------------------------------------------------------


def _parse_yaml(path: Path) -> Any:
    yaml = YAML(typ="rt")
    try:
        return yaml.load(path.read_text(encoding="utf-8"))
    except MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        line = mark.line + 1 if mark is not None else None
        problem = exc.problem or exc.context or "could not parse"
        raise ConfigError([ConfigIssue(str(path), line, "", f"invalid YAML: {problem}")]) from None
    except YAMLError as exc:
        raise ConfigError([ConfigIssue(str(path), None, "", f"invalid YAML: {exc}")]) from None


def _environment(config_dir: Path, environ: Mapping[str, str] | None) -> dict[str, str]:
    """Values from a .env file next to the config, overridden by the real environment."""
    merged: dict[str, str] = {}
    env_file = config_dir / ".env"
    if env_file.is_file():
        merged.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
    merged.update(os.environ if environ is None else environ)
    return merged


def _substitute_env(
    root: Any,
    node: Any,
    loc: Loc,
    env: Mapping[str, str],
    require_env: bool,
    file_label: str,
    issues: list[ConfigIssue],
) -> None:
    """Replace ${VAR} and ${VAR:-default} inside string values, in place."""
    if isinstance(node, dict):
        children: list[tuple[Any, Any]] = list(node.items())
    elif isinstance(node, list):
        children = list(enumerate(node))
    else:
        return

    for key, value in children:
        child_loc = (*loc, key)
        if isinstance(value, str) and "${" in value:

            def replace(match: re.Match[str], child_loc: Loc = child_loc) -> str:
                name, default = match.group(1), match.group(2)
                if name in env:
                    return env[name]
                if default is not None:
                    return default
                if require_env:
                    issues.append(
                        ConfigIssue(
                            file_label,
                            _line_for(root, child_loc),
                            _format_loc(child_loc),
                            f"environment variable {name} is not set "
                            "(add it to .env or your shell, or use --skip-env)",
                        )
                    )
                return match.group(0)

            new_value = _ENV_PATTERN.sub(replace, value)
            if new_value != value:
                node[key] = new_value
        else:
            _substitute_env(root, value, child_loc, env, require_env, file_label, issues)


# --- error reporting ------------------------------------------------------


def _issue_from_pydantic(error: Mapping[str, Any], root: Any, file_label: str) -> ConfigIssue:
    loc: Loc = tuple(error.get("loc", ()))
    kind = error.get("type", "")
    ctx = error.get("ctx") or {}
    message = str(error.get("msg", "invalid value"))

    if kind == "union_tag_invalid":
        message = (
            f"unknown check type '{ctx.get('tag')}'; expected one of: {', '.join(CHECK_TYPES)}"
        )
    elif kind == "union_tag_not_found":
        message = (
            "each check must be one key naming its type, "
            "e.g. `- freshness: {column: updated_at, max_age: 6h}`"
        )
    elif kind == "extra_forbidden":
        message = "unknown field; check the spelling"
    elif kind == "missing":
        message = "required field is missing"
    elif message.startswith("Value error, "):
        message = message.removeprefix("Value error, ")

    return ConfigIssue(file_label, _line_for(root, loc), _format_loc(loc), message)


def _cross_reference(config: SentinelConfig, root: Any, file_label: str) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    known = ", ".join(config.sources) or "none"
    for index, table in enumerate(config.tables):
        if table.source not in config.sources:
            loc: Loc = ("tables", index, "source")
            issues.append(
                ConfigIssue(
                    file_label,
                    _line_for(root, loc),
                    _format_loc(loc),
                    f"source '{table.source}' is not defined under sources (defined: {known})",
                )
            )
    return issues


def _line_for(root: Any, loc: Loc) -> int | None:
    """Walk the ruamel tree along ``loc`` and return the deepest known 1-based line."""
    node = root
    line: int | None = None
    for part in loc:
        lc = getattr(node, "lc", None)
        if isinstance(node, dict) and part in node:
            if lc is not None:
                with contextlib.suppress(KeyError, TypeError, AttributeError):
                    line = lc.key(part)[0] + 1
            node = node[part]
        elif isinstance(node, list) and isinstance(part, int) and 0 <= part < len(node):
            if lc is not None:
                with contextlib.suppress(KeyError, TypeError, AttributeError):
                    line = lc.item(part)[0] + 1
            node = node[part]
        else:
            break
    return line


def _format_loc(loc: Loc) -> str:
    text = ""
    for part in loc:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}" if text else str(part)
    return text
