"""Rule-based findings: metric/probe evidence -> root cause -> remedies."""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from ocx_diagnose.probes import (
    ContourProbe,
    contour_probe,
    degenerate_members,
    duplicate_members,
)

_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class Finding:
    id: str
    severity: str            # high | medium | low
    scope: str               # panel | plate
    subject: str             # panel id or plate id
    status: str              # likely (metrics only) | confirmed (probe evidence)
    title: str
    evidence: str
    cause: str
    mesh_steps: tuple[str, ...] = ()     # what to change in the diagnose/render settings
    source_steps: tuple[str, ...] = ()   # what to fix in the OCX source NURBS


def rank(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (_RANK[f.severity], f.id, f.subject))


def _pairs_text(pairs) -> str:
    return ", ".join(f"#{a}/#{b} ({n} samples)" for a, b, n in pairs[:5])


def _overlap(p, tol_m, cp, dups):
    if p.overlap_faces < 50:
        return None
    confirmed = bool(dups)
    ev = f"{p.overlap_faces} faces lie on another plate's surface."
    if confirmed:
        ev += f" Coincident source members: {_pairs_text(dups)}."
    return Finding(
        "overlap", "high", "plate", p.plate_id, "confirmed" if confirmed else "likely",
        "Plate overlaps neighbouring plates", ev,
        "Two or more plates (or the NURBS members behind them) cover the same part of "
        "the hull, so the shell is double-skinned there.",
        ("Overlap is geometric, not a meshing artefact; a finer tolerance will not remove it.",),
        ("Delete or merge duplicate NURBS members/plates in the OCX source.",
         "Trim each plate so adjacent plates share only an edge, not an area.",
         "Check that one plate is not modelled on both sides of the same surface."))


def _trim_reject(p, tol_m, cp, dups):
    if not p.trim_reject:
        return None
    return Finding(
        "trim-reject", "medium", "plate", p.plate_id, "likely",
        "Mesh-trim route was rejected", f"Reason: {p.trim_reject}.",
        "The plate contour could not be cut from the panel mesh, so a slower or less "
        "accurate fallback route was used.",
        ("Increase --tolerance slightly so the panel mesh is coarser at the seams.",),
        ("Make the plate contour curves lie on the NURBS surface (within 1 mm).",
         "Close the contour: end point equals start point."))


def _snap(p, tol_m, cp, dups):
    if p.snap_m is None or not p.max_snap_m or p.snap_m < 0.5 * p.max_snap_m:
        return None
    return Finding(
        "snap", "medium", "plate", p.plate_id, "likely", "Contour snaps far from the mesh",
        f"Worst snap {p.snap_m:.3g} m of allowed {p.max_snap_m:.3g} m.",
        "The plate contour does not lie on the surface the plate is cut from.",
        ("Lower --tolerance so the mesh follows the surface more closely.",),
        ("Re-project the contour curves onto the NURBS surface.",
         "Check the contour belongs to this panel's surface, not a neighbouring one."))


def _chart_distortion(p, tol_m, cp, dups):
    flipped = p.flipped_frac or 0.0
    if flipped <= 0 and (p.spread_max or 0.0) < 20:
        return None
    return Finding(
        "chart-distortion", "medium", "plate", p.plate_id, "likely",
        "Flattened chart is distorted",
        f"Flipped area {flipped:.2%}, max scale spread {p.spread_max or 0:.3g}.",
        "The surface is strongly curved or folded, so its 2-D unfolding stretches or flips.",
        ("Lower --tolerance to add triangles in high-curvature areas.",),
        ("Split the NURBS patch along the fold or ridge line.",
         "Remove near-singular corners (collapsed edges) from the patch."))


def _deviation(p, tol_m, cp, dups):
    if p.dev_max_m is None or p.dev_max_m <= tol_m:
        return None
    return Finding(
        "deviation", "medium", "plate", p.plate_id, "likely", "Mesh deviates from the surface",
        f"Max deviation {p.dev_max_m:.3g} m exceeds tolerance {tol_m:.3g} m.",
        "Triangles are too coarse for the surface curvature, or the nearest exact surface "
        "is a different member than the one meshed.",
        (f"Re-run with --tolerance below {tol_m * 1000:.0f} (mm).",),
        ("If deviation stays high at small tolerance, look for overlapping members.",))


def _non_manifold(p, tol_m, cp, dups):
    n = p.health.get("non_manifold_edges", 0)
    if n <= 0:
        return None
    return Finding(
        "non-manifold", "high", "plate", p.plate_id, "likely", "Non-manifold mesh edges",
        f"{n} edges are shared by more than two triangles.",
        "Overlapping or T-junction seams between members produce edges with 3+ faces.",
        ("Not fixable by tolerance alone.",),
        ("Make adjacent NURBS members meet along identical edge curves.",
         "Remove duplicate members covering the same area."))


def _gaps(p, tol_m, cp, dups):
    if p.gap_vertices <= 0:
        return None
    return Finding(
        "gaps", "low", "plate", p.plate_id, "likely", "Small gaps to neighbouring plates",
        f"{p.gap_vertices} boundary vertices are up to {p.max_gap_m:.3g} m from a neighbour.",
        "Neighbouring plates nearly, but not exactly, share their edges.",
        ("Gaps below the tolerance are cosmetic.",),
        ("Snap neighbouring plate contours to common edge curves.",))


def _open_contour(p, tol_m, cp, dups):
    if cp is None or cp.open_gap_m <= 10 * tol_m:
        return None
    return Finding(
        "open-contour", "high", "plate", p.plate_id, "confirmed", "Trim contour is not closed",
        f"Contour end points are {cp.open_gap_m:.3g} m apart (beyond one segment).",
        "An open contour cannot enclose an area, so trimming is unreliable.",
        (), ("Close the contour curve in the OCX source (last point = first point).",))


def _touching_contour(p, tol_m, cp, dups):
    if cp is None or cp.touching <= 0:
        return None
    return Finding(
        "self-touching-contour", "medium", "plate", p.plate_id, "confirmed",
        "Trim contour touches itself", f"{cp.touching} contour point pairs coincide.",
        "A pinched or figure-eight contour splits the plate into ambiguous regions.",
        (), ("Remove the repeated vertices or split the plate at the pinch point.",))


_PLATE_RULES = (_overlap, _trim_reject, _snap, _chart_distortion, _deviation, _non_manifold,
                _gaps, _open_contour, _touching_contour)


def plate_findings(plate, cprobe: ContourProbe | None, duplicates, tol_m: float) -> list[Finding]:
    """Findings for one plate; a failing rule is logged and skipped."""
    out = []
    for rule in _PLATE_RULES:
        try:
            f = rule(plate, tol_m, cprobe, duplicates)
        except Exception as exc:  # noqa: BLE001 — advice must never break the report
            logger.warning("advice rule {} failed on {}: {}", rule.__name__, plate.plate_id, exc)
            continue
        if f:
            out.append(f)
    return rank(out)


def panel_findings(panel_id: str, chart, duplicates, degenerate) -> list[Finding]:
    """Panel-level findings from the chart statistics and probes."""
    out = []
    if duplicates:
        out.append(Finding(
            "duplicate-members", "high", "panel", panel_id, "confirmed",
            "Duplicate NURBS members",
            f"{len(duplicates)} member pairs coincide: {_pairs_text(duplicates)}.",
            "The panel contains surfaces lying on top of each other.",
            ("Meshing cannot fix this.",),
            ("Delete the redundant member in the OCX source (keep one per area).",
             "Check the model export for repeated surfaces.")))
    if degenerate:
        out.append(Finding(
            "degenerate-members", "low", "panel", panel_id, "confirmed",
            "Degenerate NURBS members",
            f"{len(degenerate)} members have no area or no faces: "
            f"{', '.join('#' + str(i) for i in degenerate[:10])}.",
            "Collapsed or empty patches add cost and can destabilise stitching.",
            (), ("Remove zero-area members from the OCX source.",)))
    if chart is not None and chart.boundary_edges_after_stitch > 0.2 * max(
            chart.boundary_edges_before_stitch, 1):
        out.append(Finding(
            "seam-gaps", "medium", "panel", panel_id, "likely", "Seams between members stay open",
            f"{chart.boundary_edges_after_stitch} of {chart.boundary_edges_before_stitch} "
            "member boundary edges remain unstitched.",
            "Adjacent members do not share edges within the weld distance.",
            ("A coarser --tolerance widens the weld distance and may close small seams.",),
            ("Make neighbouring NURBS members share edge curves exactly.",)))
    return rank(out)


def advise_panel(panel) -> None:
    """Fill ``panel.findings`` and each plate's ``findings`` (probe failures are skipped)."""
    chart = panel.chart
    members = panel.plates[0].diag.candidates if panel.plates else []
    try:
        dups = duplicate_members(chart, members)
    except Exception as exc:  # noqa: BLE001
        logger.warning("duplicate probe failed on {}: {}", panel.panel_id, exc)
        dups = []
    try:
        degen = degenerate_members(chart)
    except Exception as exc:  # noqa: BLE001
        logger.warning("degenerate probe failed on {}: {}", panel.panel_id, exc)
        degen = []
    panel.findings = panel_findings(panel.panel_id, chart, dups, degen)
    for p in panel.plates:
        try:
            cp = contour_probe(p.diag.contour)
        except Exception as exc:  # noqa: BLE001
            logger.warning("contour probe failed on {}: {}", p.plate_id, exc)
            cp = None
        p.findings = plate_findings(p, cp, dups, panel.tol_m)
    logger.debug("advice {}: {} panel / {} plate findings", panel.panel_id,
                 len(panel.findings), sum(len(p.findings) for p in panel.plates))
