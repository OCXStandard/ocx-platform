"""Core data model for the rule engine.

All dataclasses are frozen. ``RuleSpec.params`` and ``RuleResult.findings``
hold plain data; specs are produced by the catalogue loader and (optionally)
rewritten by the user config before execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """Rule severity: wiki shall/must -> error, should -> warning, informative -> info."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RuleStatus(str, Enum):
    """Outcome of executing one rule."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_IMPLEMENTED = "not_implemented"
    SKIPPED = "skipped"
    CRASHED = "crashed"


class CheckNotImplemented(Exception):
    """Raised by stub checks; the manager maps it to RuleStatus.NOT_IMPLEMENTED."""


#: Valid entries for RuleSpec.requires.
VALID_REQUIREMENTS = frozenset({"xml", "ir", "geometry"})


@dataclass(frozen=True)
class CheckRef:
    """Reference to the executable check: a registered primitive OR a custom callable.

    Exactly one of ``primitive`` / ``custom`` must be set. ``custom`` uses the
    ``"package.module:callable"`` form.
    """

    primitive: str | None = None
    custom: str | None = None

    def __post_init__(self) -> None:
        if (self.primitive is None) == (self.custom is None):
            raise ValueError(
                "CheckRef requires exactly one of 'primitive' or 'custom'")


@dataclass(frozen=True)
class RuleSpec:
    """One rule's metadata, as loaded from a catalogue TOML file."""

    rule_id: str
    title: str
    description: str
    category: str
    severity: Severity
    source: str
    requires: frozenset[str]
    check: CheckRef
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    """One violation reported by a check."""

    message: str
    element_id: str | None = None
    guid: str | None = None
    location: int | None = None  # XML line number when available


@dataclass(frozen=True)
class RuleResult:
    """Outcome of executing one rule against one model."""

    spec: RuleSpec
    status: RuleStatus
    findings: tuple[Finding, ...] = ()
    reason: str | None = None  # set for SKIPPED / CRASHED
    duration_ms: float = 0.0


@dataclass(frozen=True)
class RulePack:
    """A named, versioned collection of rules provided by a plugin."""

    name: str
    version: str
    rules: tuple[RuleSpec, ...]
