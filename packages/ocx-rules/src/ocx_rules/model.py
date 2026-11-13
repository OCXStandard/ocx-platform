"""Core data model for the rule engine.

All dataclasses are frozen. ``RuleSpec.params``, ``RuleResult.findings`` and
``RuleResult.unchecked`` hold plain data; specs are produced by the catalogue
loader and (optionally) rewritten by the user config before execution.
``OutcomeCollector`` is the one mutable helper.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


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
    #: Supported schema families as "major.minor" prefixes; None = all versions.
    schemas: frozenset[str] | None = None


@dataclass(frozen=True)
class Finding:
    """One violation reported by a check."""

    message: str
    element_id: str | None = None
    guid: str | None = None
    location: int | None = None  # XML line number when available


@dataclass(frozen=True)
class Unchecked:
    """An element a check could not evaluate (informational)."""

    reason: str
    element_id: str | None = None
    guid: str | None = None


@dataclass(frozen=True)
class CheckOutcome:
    """Result of one check: violations plus elements it could not evaluate."""

    findings: tuple[Finding, ...] = ()
    unchecked: tuple[Unchecked, ...] = ()


class OutcomeCollector:
    """Mutable builder for a :class:`CheckOutcome` used inside checks.

    ``unchecked`` keeps one entry per element id: further reasons for the
    same id are appended with ``"; "`` (exact duplicates dropped). Entries
    without an element id are never merged.
    """

    def __init__(self, rule_id: str) -> None:
        self.rule_id = rule_id
        self._findings: list[Finding] = []
        self._unchecked: list[Unchecked] = []
        self._index: dict[str, int] = {}
        self._reasons: dict[str, list[str]] = {}

    def add(self, finding: Finding) -> None:
        self._findings.append(finding)

    def unchecked(self, reason: str, element_id: str | None = None,
                  guid: str | None = None) -> None:
        logger.debug("{}: {} not checked ({})", self.rule_id,
                     element_id or "<unidentified>", reason)
        if element_id is None:
            self._unchecked.append(Unchecked(reason, None, guid))
            return
        idx = self._index.get(element_id)
        if idx is None:
            self._index[element_id] = len(self._unchecked)
            self._reasons[element_id] = [reason]
            self._unchecked.append(Unchecked(reason, element_id, guid))
            return
        reasons = self._reasons[element_id]
        if reason in reasons:
            return
        reasons.append(reason)
        prev = self._unchecked[idx]
        self._unchecked[idx] = Unchecked("; ".join(reasons), element_id,
                                         prev.guid or guid)

    def outcome(self) -> CheckOutcome:
        return CheckOutcome(findings=tuple(self._findings),
                            unchecked=tuple(self._unchecked))


@dataclass(frozen=True)
class RuleResult:
    """Outcome of executing one rule against one model."""

    spec: RuleSpec
    status: RuleStatus
    findings: tuple[Finding, ...] = ()
    unchecked: tuple[Unchecked, ...] = ()  # PASSED / FAILED only
    reason: str | None = None  # set for SKIPPED / CRASHED
    duration_ms: float = 0.0


@dataclass(frozen=True)
class RulePack:
    """A named, versioned collection of rules provided by a plugin."""

    name: str
    version: str
    rules: tuple[RuleSpec, ...]
