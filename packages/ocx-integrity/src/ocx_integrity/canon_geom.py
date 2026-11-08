"""Canonical curve dicts; closed-contour start-point and orientation normalisation.

Points are lists of quantised decimal strings, as produced by ``Quantizer.point``.
Closed rings start at the lexicographically smallest point. If the dominant
Newell-normal component (ties x > y > z) is negative, the orientation is reversed.
Open curves and NURBS are kept as given.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from ocx_model_core.model.ir import IrCompositeCurve3D, IrCurve3D, IrPolyLine3D

from ocx_integrity.jsonutil import dataclass_dict, prune
from ocx_integrity.profile import DEFAULT_DECIMALS
from ocx_integrity.quantize import fmt_decimal

Canon = Callable[[Any], Any]
Point = list[str]

CLOSURE_TOL = Decimal("0.000001")  # 1 µm in SI metres


def curve_record(curve: IrCurve3D, canon: Canon) -> dict[str, Any]:
    if isinstance(curve, IrPolyLine3D):
        return _polyline(curve, canon)
    if isinstance(curve, IrCompositeCurve3D):
        return _composite(curve, canon)
    return dataclass_dict(curve, canon)


# --- point helpers -----------------------------------------------------------


def _key(p: Point) -> tuple[Decimal, ...]:
    return tuple(Decimal(c) for c in p[:3])


def _same(a: Point | None, b: Point | None) -> bool:
    # Unknown-unit points carry a raw unit id at index 3; only equal ids are comparable.
    if a is None or b is None or a[3:] != b[3:]:
        return False
    return all(abs(Decimal(x) - Decimal(y)) <= CLOSURE_TOL for x, y in zip(a[:3], b[:3]))


def _rotate_min(pts: list[Point]) -> list[Point]:
    i = min(range(len(pts)), key=lambda k: _key(pts[k]))
    return pts[i:] + pts[:i]


def _newell(pts: list[Point]) -> tuple[float, float, float]:
    nx = ny = nz = 0.0
    for i, cur in enumerate(pts):
        nxt = pts[(i + 1) % len(pts)]
        x1, y1, z1 = (float(c) for c in cur[:3])
        x2, y2, z2 = (float(c) for c in nxt[:3])
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return nx, ny, nz


def _dominant_negative(n: tuple[float, float, float]) -> bool:
    i = max(range(3), key=lambda k: (abs(n[k]), -k))  # ties resolved x > y > z
    return n[i] < 0


# --- polylines ---------------------------------------------------------------


def _polyline(curve: IrPolyLine3D, canon: Canon) -> dict[str, Any]:
    pts: list[Point] = [canon(p) for p in curve.vertices]
    repeated = len(pts) > 1 and _same(pts[0], pts[-1])
    closed = bool(curve.is_closed) or (len(pts) > 3 and repeated)
    if closed and repeated:
        pts = pts[:-1]
    if closed and len(pts) >= 3:
        pts = _rotate_min(pts)
        if _dominant_negative(_newell(pts)):
            pts = _rotate_min(pts[::-1])
    return prune({"type": "polyline3d", "vertices": pts, "is_closed": closed})


# --- composite curves --------------------------------------------------------


def _endpoints(seg: dict[str, Any]) -> tuple[Point, Point] | None:
    t = seg.get("type")
    if t in ("line3d", "circumarc3d"):
        start, end = seg.get("start"), seg.get("end")
    elif t == "polyline3d" and not seg.get("is_closed") and seg.get("vertices"):
        start, end = seg["vertices"][0], seg["vertices"][-1]
    elif t == "nurbs3d" and seg.get("control_points"):
        start, end = seg["control_points"][0], seg["control_points"][-1]
    else:
        return None
    if start is None or end is None:
        return None
    return start, end


def _seg_points(seg: dict[str, Any]) -> list[Point]:
    """Ordered points of a segment, excluding its end point (for the Newell normal)."""
    t = seg["type"]
    if t == "line3d":
        return [seg["start"]]
    if t == "circumarc3d":
        return [seg["start"]] + ([seg["intermediate"]] if "intermediate" in seg else [])
    if t == "polyline3d":
        return seg["vertices"][:-1]
    return seg["control_points"][:-1]  # nurbs3d


def _reverse_seg(seg: dict[str, Any]) -> dict[str, Any] | None:
    t = seg.get("type")
    out = dict(seg)
    if t in ("line3d", "circumarc3d"):
        out["start"], out["end"] = seg.get("end"), seg.get("start")
        return prune(out)
    if t == "polyline3d":
        out["vertices"] = seg["vertices"][::-1]
        return out
    if t == "nurbs3d":
        out["control_points"] = seg["control_points"][::-1]
        if "weights" in seg:
            out["weights"] = seg["weights"][::-1]
        if "knot_vector" in seg:
            kv = [Decimal(k) for k in seg["knot_vector"]]
            lo, hi = kv[0], kv[-1]
            out["knot_vector"] = [fmt_decimal(lo + hi - k, DEFAULT_DECIMALS) for k in kv[::-1]]
        return out
    return None


def _rotate_segs(segs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    i = min(range(len(segs)), key=lambda k: _key(_endpoints(segs[k])[0]))
    return segs[i:] + segs[:i]


def _composite(curve: IrCompositeCurve3D, canon: Canon) -> dict[str, Any]:
    segs = [curve_record(s, canon) for s in curve.segments]
    ends = [_endpoints(s) for s in segs]
    closed = bool(segs) and all(e is not None for e in ends) and _same(ends[-1][1], ends[0][0])
    if closed:
        segs = _rotate_segs(segs)
        pts = [p for s in segs for p in _seg_points(s)]
        if len(pts) >= 3 and _dominant_negative(_newell(pts)):
            reversed_segs = [_reverse_seg(s) for s in reversed(segs)]
            if all(r is not None for r in reversed_segs):
                segs = _rotate_segs(reversed_segs)
    return prune({"type": "compositecurve3d", "segments": segs})
