"""Property consistency checks (OCX-PROP-001 through 004)."""
from __future__ import annotations

from typing import Any

import numpy as np
from loguru import logger
from ocx_geometry.measure import surface_area
from ocx_geometry.sections_2d import section_polygon
from ocx_geometry.topology2d import polygon_ok
from ocx_model_core.model.ir.base import ParentKind

from ocx_rules.model import Finding
from ocx_rules.packs.best_practice.checks.topology import _placed_hole_outlines
from ocx_rules.xml_index import localname


def _declared_weight_kg(geo, mass_properties) -> float | None:
    """Declared dry weight in kg (moulded first, physical fallback)."""
    if mass_properties is None:
        return None
    return geo.to_si(mass_properties.moulded_dry_weight
                     or mass_properties.physical_dry_weight)


def _declared_cog(mass_properties):
    if mass_properties is None:
        return None
    return mass_properties.moulded_cog or mass_properties.physical_cog


def _cog_m(length, cog) -> np.ndarray:
    """IrCog -> (3,) point in metres."""
    return np.array([length.to_m(cog.x, cog.unit),
                     length.to_m(cog.y, cog.unit),
                     length.to_m(cog.z, cog.unit)], dtype=float)


def _open_uv(ring: np.ndarray) -> np.ndarray:
    """Drop a repeated closing UV point (surface_area wants open rings)."""
    if len(ring) > 3 and np.linalg.norm(ring[0] - ring[-1]) < 1e-12:
        return ring[:-1]
    return ring


def plate_weight_consistent(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-PROP-001: plate weight ~= area x thickness x density."""
    tol = float(params.get("relative_tolerance", 0.02))
    findings: list[Finding] = []
    geo = context.geometry
    vessel = context.vessel
    for pid, plate in vessel.plates.items():
        declared = _declared_weight_kg(geo, plate.mass_properties)
        if declared is None or declared <= 0.0:
            logger.debug("PROP-001: plate {} skipped (no declared dry "
                         "weight)", pid)
            continue
        thickness = geo.length.qty(plate.thickness)
        if thickness is None:
            logger.debug("PROP-001: plate {} skipped (no thickness)", pid)
            continue
        material = (vessel.materials.get(plate.material_ref.local_ref)
                    if plate.material_ref is not None else None)
        density = geo.to_si(material.density) if material is not None else None
        if density is None:
            logger.debug("PROP-001: plate {} skipped (no material density)",
                         pid)
            continue
        panel = None
        pr = plate.parent_ref
        if pr is not None and pr.kind == ParentKind.PANEL:
            panel = vessel.panels.get(pr.id)
        if panel is None:
            logger.debug("PROP-001: plate {} skipped (no owning panel)", pid)
            continue
        param = geo.surface_param(geo.panel_surface(panel))
        if param is None:
            logger.debug("PROP-001: plate {} skipped (no buildable panel "
                         "surface)", pid)
            continue
        if param.periodic_u:
            logger.debug("PROP-001: plate {} skipped (periodic surface, "
                         "ambiguous UV mapping)", pid)
            continue
        outline = geo.sample(plate.outer_contour)
        if outline is None or len(outline) < 3:
            logger.debug("PROP-001: plate {} skipped (unsampleable outer "
                         "contour)", pid)
            continue
        holes_3d, skipped = _placed_hole_outlines(
            context, plate.cut_by_holes, plate.cut_by_contours)
        if skipped:
            logger.debug("PROP-001: plate {}: {} hole(s) could not be "
                         "placed; ignored in the area", pid, skipped)
        try:
            outline_uv = _open_uv(np.asarray(param.inverse(outline),
                                             dtype=float))
            holes_uv = [_open_uv(np.asarray(param.inverse(h), dtype=float))
                        for h in holes_3d]
            area = surface_area(param, outline_uv, holes_uv)
        except Exception as exc:  # noqa: BLE001 — lean-pass on UV failure
            logger.debug("PROP-001: plate {} skipped (area evaluation "
                         "failed: {})", pid, exc)
            continue
        if not np.isfinite(area) or area <= 0.0:
            logger.debug("PROP-001: plate {} skipped (degenerate computed "
                         "area {})", pid, area)
            continue
        computed = area * thickness * density
        if abs(computed - declared) / declared > tol:
            findings.append(Finding(
                message=(f"Plate declared dry weight {declared:.2f} kg "
                         f"deviates from computed area x thickness x density "
                         f"= {computed:.2f} kg by more than {tol * 100:.0f}%"),
                element_id=pid, guid=plate.guidref))
    return findings


def panel_weight_cog_consistent(context,
                                params: dict[str, Any]) -> list[Finding]:
    """OCX-PROP-002: panel weight/CoG consistent with all its children."""
    tol = float(params.get("relative_tolerance", 0.02))
    cog_tol_m = float(params.get("cog_tolerance_mm", 50.0)) / 1000.0
    findings: list[Finding] = []
    geo = context.geometry
    vessel = context.vessel
    for pid, panel in vessel.panels.items():
        panel_mass = _declared_weight_kg(geo, panel.mass_properties)
        panel_cog = _declared_cog(panel.mass_properties)
        if panel_mass is None and panel_cog is None:
            logger.debug("PROP-002: panel {} skipped (no declared mass "
                         "properties)", pid)
            continue
        # A panel's declared mass covers the complete panel: all children
        # parented to it (plates, stiffeners, edge reinforcements,
        # brackets, pillars).
        children: list[tuple[float, Any]] = []
        for part in (*vessel.plates.values(), *vessel.stiffeners.values(),
                     *vessel.edge_reinforcements.values(),
                     *vessel.brackets.values(), *vessel.pillars.values()):
            pr = part.parent_ref
            if pr is None or pr.kind != ParentKind.PANEL or pr.id != pid:
                continue
            mass = _declared_weight_kg(geo, part.mass_properties)
            if mass is None:
                continue
            children.append((mass, _declared_cog(part.mass_properties)))
        if not children:
            logger.debug("PROP-002: panel {} skipped (no children with "
                         "declared mass)", pid)
            continue
        total = sum(m for m, _ in children)
        if panel_mass is not None and panel_mass > 0.0:
            if abs(total - panel_mass) / panel_mass > tol:
                findings.append(Finding(
                    message=(f"Panel declared dry weight {panel_mass:.2f} kg "
                             f"deviates from the sum of its child part weights "
                             f"{total:.2f} kg by more than {tol * 100:.0f}%"),
                    element_id=pid, guid=panel.guidref))
        if panel_cog is not None:
            weighted = [(m, _cog_m(geo.length, c)) for m, c in children
                        if c is not None]
            w_total = sum(m for m, _ in weighted)
            if weighted and w_total > 0.0:
                child_cog = sum(m * p for m, p in weighted) / w_total
                dist = float(np.linalg.norm(
                    child_cog - _cog_m(geo.length, panel_cog)))
                if dist > cog_tol_m:
                    findings.append(Finding(
                        message=(f"Panel centre of gravity deviates from the "
                                 f"mass-weighted child centre of gravity by "
                                 f"{dist * 1000:.1f} mm, exceeding "
                                 f"{cog_tol_m * 1000:.1f} mm"),
                        element_id=pid, guid=panel.guidref))
    return findings


def profile_closed_section(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-PROP-003: section parameters must yield a closed valid profile."""
    findings: list[Finding] = []
    geo = context.geometry
    for sid, section in context.vessel.sections.items():
        try:
            poly = section_polygon(section, geo.length)
        except Exception as exc:  # noqa: BLE001 — lean-pass per section
            logger.debug("PROP-003: section {} skipped (profile build "
                         "failed: {})", sid, exc)
            continue
        if poly is None:
            logger.debug("PROP-003: section {} skipped (profile could not "
                         "be built)", sid)
            continue
        reason = polygon_ok(poly)
        if reason is not None:
            findings.append(Finding(
                message=(f"Section profile is not a closed valid polygon: "
                         f"{reason}"),
                element_id=sid, guid=section.guidref))
    return findings


def _any_instance_renewal(vessel) -> bool:
    for part in (*vessel.plates.values(), *vessel.brackets.values()):
        if part.renewal_thickness is not None:
            return True
    for part in (*vessel.stiffeners.values(), *vessel.pillars.values(),
                 *vessel.edge_reinforcements.values()):
        if (part.web_renewal_thickness is not None
                or part.flange_renewal_thickness is not None):
            return True
    return False


def renewal_thickness_on_instance(context, params: dict) -> list[Finding]:
    """OCX-PROP-004: renewal thickness must reach the part instance.

    The IR builder only picks up instance-level renewal thickness (part
    attributes or the per-instance SectionRef). If the document declares
    renewal-thickness elements but no instance carries any, the values live
    only on a shared definition — one finding per declaration.
    """
    if _any_instance_renewal(context.vessel):
        return []
    findings = []
    for el in context.xml_index.root.iter():
        tag = localname(el.tag)
        if "RenewalThickness" in tag:
            findings.append(Finding(
                message=(f"<{tag}> at line {el.sourceline} declares renewal thickness "
                         f"on a shared definition only; assign it to the individual "
                         f"part instance"),
                location=el.sourceline))
    return findings
