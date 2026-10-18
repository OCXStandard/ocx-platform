"""Load and validate declarative rule-catalogue TOML files.

All structural problems (unknown primitive, unimportable custom reference,
duplicate ids, invalid severity/category/requires) are hard errors raised at
load time — never at run time.
"""
from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

from loguru import logger

from ocx_rules.model import VALID_REQUIREMENTS, CheckRef, RuleSpec, Severity


class CatalogueError(ValueError):
    """A rule catalogue file is structurally invalid."""


def resolve_custom(ref: str):
    """Import and return the callable behind a ``"module:attr"`` reference."""
    try:
        module_name, _, attr = ref.partition(":")
        if not module_name or not attr:
            raise ImportError(f"malformed custom reference {ref!r}")
        fn = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise CatalogueError(f"cannot import custom check {ref!r}: {exc}") from exc
    if not callable(fn):
        raise CatalogueError(f"custom check {ref!r} is not callable")
    return fn


def _parse_check(raw: dict, rule_id: str, source_name: str) -> tuple[CheckRef, dict]:
    from ocx_rules.primitives import PRIMITIVE_REGISTRY

    primitive = raw.get("primitive")
    custom = raw.get("custom")
    if (primitive is None) == (custom is None):
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} check needs exactly one of "
            f"'primitive' or 'custom'")
    if primitive is not None and primitive not in PRIMITIVE_REGISTRY:
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} uses unknown primitive {primitive!r}")
    if custom is not None:
        resolve_custom(custom)  # import check at load time
    params = {k: v for k, v in raw.items() if k not in ("primitive", "custom")}
    return CheckRef(primitive=primitive, custom=custom), params


def _parse_rule(raw: dict, source_name: str) -> RuleSpec:
    for key in ("id", "title", "description", "source", "category",
                "severity", "requires", "check"):
        if key not in raw:
            raise CatalogueError(
                f"{source_name}: rule {raw.get('id', '<missing id>')!r} "
                f"lacks required key {key!r}")
    rule_id = raw["id"]
    if not isinstance(rule_id, str) or not rule_id:
        raise CatalogueError(f"{source_name}: rule id must be a non-empty string")
    if not isinstance(raw["category"], str) or not raw["category"]:
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} category must be a non-empty string")
    try:
        severity = Severity(raw["severity"])
    except ValueError as exc:
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} has invalid severity "
            f"{raw['severity']!r}") from exc
    requires = frozenset(raw["requires"])
    unknown = requires - VALID_REQUIREMENTS
    if unknown:
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} has unknown requires {sorted(unknown)}")
    check, params = _parse_check(raw["check"], rule_id, source_name)
    return RuleSpec(
        rule_id=rule_id,
        title=raw["title"],
        description=raw["description"],
        category=raw["category"],
        severity=severity,
        source=raw["source"],
        requires=requires,
        check=check,
        params=params,
    )


def parse_rules_toml(text: str, source_name: str) -> list[RuleSpec]:
    """Parse one TOML document into validated RuleSpecs."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise CatalogueError(f"{source_name}: invalid TOML: {exc}") from exc
    specs = [_parse_rule(raw, source_name) for raw in data.get("rule", [])]
    seen: set[str] = set()
    for spec in specs:
        if spec.rule_id in seen:
            raise CatalogueError(
                f"{source_name}: duplicate rule id {spec.rule_id!r}")
        seen.add(spec.rule_id)
    return specs


def load_catalogue_dir(directory) -> tuple[RuleSpec, ...]:
    """Load every ``*.toml`` in *directory* (Path or importlib Traversable)."""
    specs: list[RuleSpec] = []
    seen: set[str] = set()
    entries = sorted(
        (e for e in directory.iterdir() if e.name.endswith(".toml")),
        key=lambda e: e.name,
    )
    for entry in entries:
        for spec in parse_rules_toml(entry.read_text(encoding="utf-8"), entry.name):
            if spec.rule_id in seen:
                raise CatalogueError(
                    f"{entry.name}: duplicate rule id {spec.rule_id!r} "
                    f"(already defined in another file)")
            seen.add(spec.rule_id)
            specs.append(spec)
    logger.debug("Loaded {} rules from catalogue {}", len(specs), directory)
    return tuple(specs)
