"""RuleManager — plugin discovery, configuration, filtering and execution.

Each rule executes in isolation: an exception becomes a CRASHED result,
CheckNotImplemented becomes NOT_IMPLEMENTED, unsatisfied requirements become
SKIPPED. The run never aborts because of one rule.
"""
from __future__ import annotations

import importlib.util
import time
from importlib.metadata import entry_points

from loguru import logger

from ocx_rules.catalogue import CatalogueError, resolve_custom
from ocx_rules.config import RuleConfig, apply_config
from ocx_rules.context import ValidationContext
from ocx_rules.model import (
    CheckNotImplemented,
    CheckRef,
    RulePack,
    RuleResult,
    RuleSpec,
    RuleStatus,
)

ENTRY_POINT_GROUP = "ocx_rules.packs"


def _resolve_check(check: CheckRef):
    if check.primitive is not None:
        from ocx_rules.primitives import PRIMITIVE_REGISTRY

        return PRIMITIVE_REGISTRY[check.primitive]
    return resolve_custom(check.custom)


class RuleManager:
    """Discover rule packs, apply configuration and execute rules."""

    def __init__(self, config: RuleConfig | None = None,
                 packs: list[RulePack] | None = None) -> None:
        self._config = config or RuleConfig()
        self._packs = packs  # None -> discover() on first use

    def discover(self) -> list[RulePack]:
        """Load every pack registered under the ``ocx_rules.packs`` entry-point group."""
        packs: list[RulePack] = []
        for ep in sorted(entry_points(group=ENTRY_POINT_GROUP), key=lambda e: e.name):
            pack = ep.load()()
            logger.debug("Discovered rule pack {!r} v{} ({} rules)",
                         pack.name, pack.version, len(pack.rules))
            packs.append(pack)
        self._packs = packs
        return packs

    def rules(self, *, category: str | None = None,
              rule_id: str | None = None) -> list[RuleSpec]:
        """All enabled rules after config, optionally filtered."""
        if self._packs is None:
            self.discover()
        specs: list[RuleSpec] = []
        seen: set[str] = set()
        for pack in self._packs:
            for spec in pack.rules:
                if spec.rule_id in seen:
                    raise CatalogueError(
                        f"duplicate rule id {spec.rule_id!r} across packs")
                seen.add(spec.rule_id)
                specs.append(spec)
        specs = apply_config(specs, self._config)
        if category is not None:
            specs = [s for s in specs if s.category == category]
        if rule_id is not None:
            specs = [s for s in specs if s.rule_id == rule_id]
        return specs

    def run(self, context: ValidationContext, *, category: str | None = None,
            rule_id: str | None = None) -> list[RuleResult]:
        """Execute every enabled (filtered) rule against *context*."""
        return [self._run_one(spec, context)
                for spec in self.rules(category=category, rule_id=rule_id)]

    def _run_one(self, spec: RuleSpec, context: ValidationContext) -> RuleResult:
        start = time.perf_counter()

        def done(status: RuleStatus, findings=(), reason=None) -> RuleResult:
            return RuleResult(
                spec=spec, status=status, findings=tuple(findings), reason=reason,
                duration_ms=(time.perf_counter() - start) * 1000.0)

        reason = self._unsatisfied(spec, context)
        if reason is not None:
            logger.debug("Rule {} skipped: {}", spec.rule_id, reason)
            return done(RuleStatus.SKIPPED, reason=reason)
        try:
            check = _resolve_check(spec.check)
            findings = check(context, dict(spec.params))
        except CheckNotImplemented as exc:
            return done(RuleStatus.NOT_IMPLEMENTED, reason=str(exc))
        except Exception as exc:
            logger.warning("Rule {} crashed: {}", spec.rule_id, exc)
            return done(RuleStatus.CRASHED, reason=f"{type(exc).__name__}: {exc}")
        return done(RuleStatus.FAILED if findings else RuleStatus.PASSED,
                    findings=findings)

    @staticmethod
    def _unsatisfied(spec: RuleSpec, context: ValidationContext) -> str | None:
        if "xml" in spec.requires:
            try:
                context.xml_tree  # noqa: B018 — triggers lazy parse
            except Exception as exc:
                return f"cannot parse XML: {exc}"
        if "ir" in spec.requires:
            try:
                context.vessel  # noqa: B018 — triggers lazy build
            except Exception as exc:
                return f"cannot build IR: {exc}"
        if "geometry" in spec.requires and importlib.util.find_spec("ocx_geometry") is None:
            return "ocx-geometry is not installed"
        return None
