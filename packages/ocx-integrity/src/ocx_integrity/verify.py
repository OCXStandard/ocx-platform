"""Verify a model against a stored manifest."""

from __future__ import annotations

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.diff import ChangeReport, diff_manifests
from ocx_integrity.manifest import Manifest, build_manifest


def verify_model(vessel: IrVessel, manifest: Manifest, key: bytes) -> ChangeReport:
    """Rebuild the manifest from ``vessel`` and diff it against ``manifest`` (A = stored)."""
    return diff_manifests(manifest, build_manifest(vessel, key))
