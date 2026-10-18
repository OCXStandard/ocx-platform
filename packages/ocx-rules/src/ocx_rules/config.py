"""User configuration: enable/disable rules, override severity and parameters.

Format (``ocx-rules.toml``)::

    [rules]
    disable = ["OCX-PROP-001"]

    [rules.overrides.OCX-TOP-001]
    severity     = "warning"
    tolerance_mm = 0.5

Overrides may change severity and any check parameter; never the check itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import tomllib
from loguru import logger

from ocx_rules.model import RuleSpec, Severity


class ConfigError(ValueError):
    """The user configuration file is invalid or unreadable."""


@dataclass(frozen=True)
class RuleConfig:
    """Parsed user configuration; the default is a no-op."""

    disabled: frozenset[str] = frozenset()
    overrides: dict[str, dict] = field(default_factory=dict)


def load_config(path: Path | None) -> RuleConfig:
    """Load *path*; ``None`` returns the empty (no-op) config."""
    if path is None:
        return RuleConfig()
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    rules = data.get("rules", {})
    overrides = rules.get("overrides", {})
    for rule_id, override in overrides.items():
        if "severity" in override:
            try:
                Severity(override["severity"])
            except ValueError as exc:
                raise ConfigError(
                    f"{path}: override for {rule_id!r} has invalid severity "
                    f"{override['severity']!r}") from exc
    cfg = RuleConfig(
        disabled=frozenset(rules.get("disable", [])),
        overrides=dict(overrides),
    )
    logger.debug("Loaded rule config from {}: {} disabled, {} overridden",
                 path, len(cfg.disabled), len(cfg.overrides))
    return cfg


def apply_config(specs: list[RuleSpec], config: RuleConfig) -> list[RuleSpec]:
    """Drop disabled rules and apply severity/param overrides."""
    out: list[RuleSpec] = []
    for spec in specs:
        if spec.rule_id in config.disabled:
            continue
        override = config.overrides.get(spec.rule_id)
        if override:
            severity = (Severity(override["severity"])
                        if "severity" in override else spec.severity)
            params = {**spec.params,
                      **{k: v for k, v in override.items() if k != "severity"}}
            spec = replace(spec, severity=severity, params=params)
        out.append(spec)
    return out
