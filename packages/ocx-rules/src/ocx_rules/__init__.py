"""ocx-rules — configurable best-practice rule engine for OCX models.

Public API re-exported here; see the design spec in
docs/superpowers/specs/2026-10-18-ocx-rule-validation-design.md.
"""
from __future__ import annotations

from ocx_rules.catalogue import CatalogueError, load_catalogue_dir, parse_rules_toml
from ocx_rules.config import ConfigError, RuleConfig, apply_config, load_config
from ocx_rules.context import ValidationContext
from ocx_rules.manager import RuleManager
from ocx_rules.model import (
    CheckNotImplemented,
    CheckOutcome,
    CheckRef,
    Finding,
    OutcomeCollector,
    RulePack,
    RuleResult,
    RuleSpec,
    RuleStatus,
    Severity,
    Unchecked,
)

__version__ = "0.1.0"

__all__ = [
    "CatalogueError",
    "CheckNotImplemented",
    "CheckOutcome",
    "CheckRef",
    "ConfigError",
    "Finding",
    "OutcomeCollector",
    "RuleConfig",
    "RuleManager",
    "RulePack",
    "RuleResult",
    "RuleSpec",
    "RuleStatus",
    "Severity",
    "Unchecked",
    "ValidationContext",
    "apply_config",
    "load_catalogue_dir",
    "load_config",
    "parse_rules_toml",
]
