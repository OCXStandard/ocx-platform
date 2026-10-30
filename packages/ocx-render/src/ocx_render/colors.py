"""Colour schemes applied to rendered parts before export.

``thickness`` (default): plates and brackets get one distinct colour per
plate thickness, assigned in thickness order from ``THICKNESS_PALETTE``;
stiffeners and pillars share one shade of their kind colour per section.
Parts therefore share materials, and the returned legend lets the viewer
explain (and isolate) each colour.

``part``: keep the per-part colours ``PartMesh`` assigns on construction.
"""
from __future__ import annotations

from loguru import logger
from ocx_geometry.mesh import PartMesh, part_color

COLOR_SCHEMES = ("thickness", "part")

# Greedy max-min separation in OKLab within a band readable on the viewer's
# dark background (0.55 < L < 0.85, chroma > 0.09).  Prefixes stay well
# separated: worst pair ΔE 34.9 for the first 4, 21.5 for 8, 14.3 for 17.
# No 17-colour set is colour-blind safe, hence the isolating viewer legend.
THICKNESS_PALETTE = (
    "#ff00ff", "#00f500", "#996614", "#0066ff", "#8fd6ff",
    "#ffad00", "#ff005c", "#00ad52", "#ad7ac2", "#9900f5",
    "#ffa3ff", "#008599", "#c20a99", "#3da3ff", "#a3e08f",
    "#f58585", "#ad9914", "#29c2b8", "#b8475c", "#ff5cc2",
)
NO_THICKNESS = (150, 150, 150)

_THICKNESS_KINDS = ("plate", "bracket")
_SECTION_KINDS = ("stiffener", "pillar")


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def apply_color_scheme(meshes: list[PartMesh], scheme: str) -> list[dict]:
    """Recolour ``meshes`` in place; returns the legend (empty for ``part``).

    Legend entries: ``{"label", "thickness_mm", "color", "count"}`` in
    thickness order, with a final ``thickness_mm: None`` entry for plates
    and brackets that have no thickness.
    """
    if scheme not in COLOR_SCHEMES:
        raise ValueError(f"unknown colour scheme {scheme!r}; "
                         f"expected one of {COLOR_SCHEMES}")
    if scheme == "part":
        return []

    by_thickness = [m for m in meshes if m.kind in _THICKNESS_KINDS]
    values = sorted({m.extras.get("thickness_mm") for m in by_thickness}
                    - {None})
    if len(values) > len(THICKNESS_PALETTE):
        logger.warning("{} distinct thicknesses but {} palette colours; "
                       "colours repeat (use the viewer legend to isolate)",
                       len(values), len(THICKNESS_PALETTE))
    color_of = {v: _rgb(THICKNESS_PALETTE[i % len(THICKNESS_PALETTE)])
                for i, v in enumerate(values)}
    color_of[None] = NO_THICKNESS
    counts: dict[float | None, int] = {}
    for m in by_thickness:
        t = m.extras.get("thickness_mm")
        m.color = color_of[t]
        counts[t] = counts.get(t, 0) + 1

    for m in meshes:
        if m.kind in _SECTION_KINDS:
            m.color = part_color(m.kind, m.extras.get("section") or "")

    legend = [{"label": f"{v:g} mm", "thickness_mm": v,
               "color": _hex(color_of[v]), "count": counts[v]} for v in values]
    if None in counts:
        legend.append({"label": "no thickness", "thickness_mm": None,
                       "color": _hex(NO_THICKNESS), "count": counts[None]})
    return legend
