"""Pure-Python UV-domain tessellation backend.

Pipeline per part: inverse-map boundary (and holes) to UV → repair the UV
polygon with shapely → earcut-triangulate → metric subdivision for curved
surfaces → evaluate surface at final UV vertices → PartMesh.

Multi-patch charts are clipped to source faces before triangulation and
refined in each source member's UV, never across chart seams or holes.
"""
from __future__ import annotations

from collections.abc import Iterable

import mapbox_earcut
import numpy as np
import shapely
import trimesh
from loguru import logger
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from ocx_geometry.backend import ITessellator, TessellationOptions
from ocx_geometry.lscm import LscmParam
from ocx_geometry.mesh import PartMesh
from ocx_geometry.surfaces import SurfaceParam

_MIN_TRI_AREA = 1e-14


def _polygon_parts(geom) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom]
    if hasattr(geom, "geoms"):                 # MultiPolygon/GeometryCollection
        return [g for g in geom.geoms if isinstance(g, Polygon)]
    return []


def _clean_polygon(uv: np.ndarray, holes: list[np.ndarray]
                   ) -> list[tuple[np.ndarray, list[np.ndarray]]]:
    """Validate/repair the UV polygon; return (exterior, holes) ring arrays
    for every usable polygon part.

    A locally folded development splits into several parts under
    ``make_valid``; all parts belong to the plate and must be kept.
    """
    try:
        poly = Polygon(uv, holes=[h for h in holes if len(h) >= 3])
    except (ValueError, TypeError):
        return []
    if poly.is_valid:
        parts = [poly]
    else:
        try:
            parts = _polygon_parts(shapely.make_valid(poly))
        except shapely.errors.GEOSException as exc:
            logger.debug("GEOSException during make_valid: {}", exc)
            return []
    largest = max((p.area for p in parts), default=0.0)
    out = []
    for p in parts:
        if p.is_empty or p.area <= max(0.0, 1e-9 * largest):
            continue
        p = orient(p, sign=1.0)                  # CCW exterior, CW holes
        ext = np.array(p.exterior.coords)[:-1]
        ints = [np.array(r.coords)[:-1] for r in p.interiors]
        if len(ext) >= 3:
            out.append((ext, ints))
    return out


def _earcut(ext: np.ndarray, holes: list[np.ndarray]
            ) -> tuple[np.ndarray, np.ndarray] | None:
    rings = [ext] + holes
    verts = np.vstack(rings).astype(np.float64)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    tris = mapbox_earcut.triangulate_float64(verts, ends)
    if len(tris) == 0:
        return None
    return verts, np.asarray(tris, dtype=np.int64).reshape(-1, 3)


def _drop_degenerate(verts3: np.ndarray, tris: np.ndarray) -> np.ndarray:
    cross = np.cross(verts3[tris[:, 1]] - verts3[tris[:, 0]],
                     verts3[tris[:, 2]] - verts3[tris[:, 0]])
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    return tris[areas > _MIN_TRI_AREA]


def _shift_hole_to_periodic_range(hole_uv: np.ndarray, ext_uv: np.ndarray,
                                   periodic_u: bool) -> np.ndarray:
    """For periodic-u surfaces, shift hole u-range to be near exterior u-range.

    When exterior contour crosses a seam (e.g. u=π on a cylinder), its unwrapped
    u-range may span a wide interval. Each hole is inverted independently and
    may land in a different 2π branch. This function shifts the hole by ±2π so
    its mean u falls within or nearest the exterior u-range.
    """
    if not periodic_u or len(ext_uv) == 0 or len(hole_uv) == 0:
        return hole_uv

    ext_u_min, ext_u_max = float(np.min(ext_uv[:, 0])), float(np.max(ext_uv[:, 0]))
    hole_u_min, hole_u_max = float(np.min(hole_uv[:, 0])), float(np.max(hole_uv[:, 0]))
    hole_u_mean = (hole_u_min + hole_u_max) / 2.0
    ext_u_mean = (ext_u_min + ext_u_max) / 2.0

    # Find k such that hole_u_mean + k*2π is closest to ext_u_mean
    k = np.round((ext_u_mean - hole_u_mean) / (2.0 * np.pi))
    shift = float(k) * 2.0 * np.pi
    result = hole_uv.copy()
    result[:, 0] += shift
    return result


class UvTessellator(ITessellator):
    """Default pure-Python tessellation backend."""

    def tessellate_trimmed_surface(
        self,
        part_id: str,
        name: str,
        kind: str,
        contour_pts: np.ndarray,
        hole_pts: list[np.ndarray],
        surface_param: SurfaceParam,
        options: TessellationOptions,
    ) -> PartMesh | None:
        try:
            uv = surface_param.inverse(contour_pts)
            uv_holes = [surface_param.inverse(h) for h in hole_pts]
        except Exception as exc:                      # inversion is best-effort
            logger.debug("UV inversion failed for {}: {}", part_id, exc)
            return None

        # ISSUE 3: Check for non-finite UVs (NaN/inf) immediately after inversion
        if not np.all(np.isfinite(uv)):
            logger.debug("Non-finite UV values in exterior contour for {}", part_id)
            return None

        # ISSUE 1: For periodic-u surfaces, shift holes to the exterior u-range
        periodic_u = getattr(surface_param, "periodic_u", False)
        valid_holes = []
        for i, hole_uv in enumerate(uv_holes):
            if not np.all(np.isfinite(hole_uv)):
                logger.debug("Skipping hole {} for {} (non-finite UV values)",
                             i, part_id)
                continue
            if periodic_u:
                hole_uv = _shift_hole_to_periodic_range(hole_uv, uv, periodic_u)
            valid_holes.append(hole_uv)

        if len(valid_holes) < len(uv_holes):
            logger.debug("Dropped {} holes for {} due to non-finite UVs",
                         len(uv_holes) - len(valid_holes), part_id)

        parts = _clean_polygon(uv, valid_holes)
        if not parts:
            logger.debug("Unrepairable UV polygon for {}", part_id)
            return None

        # Log if make_valid dropped interior rings
        n_ints = sum(len(ints) for _, ints in parts)
        if n_ints < len(valid_holes):
            logger.debug("UV cleaning dropped {} interior ring(s) for {} "
                         "(holes outside the plate region are expected to be "
                         "dropped)", len(valid_holes) - n_ints, part_id)

        regions: Iterable[tuple[SurfaceParam, np.ndarray, list[np.ndarray], np.ndarray | None]]
        if isinstance(surface_param, LscmParam):
            polygon = shapely.union_all([Polygon(ext, ints) for ext, ints in parts])
            try:
                regions = list(surface_param.trimmed_regions(polygon))
            except (ValueError, shapely.errors.GEOSException) as exc:
                logger.warning("Chart trim failed for {}: {}", part_id, exc)
                return None
        else:
            regions = ((surface_param, ext, ints, None) for ext, ints in parts)

        vert_blocks, tri_blocks, normal_blocks, offset = [], [], [], 0
        for param, ext, ints, reference_normal in regions:
            cut = _earcut(ext, ints)
            if cut is None:
                continue
            verts_uv, tris = cut
            # Refine in source-member metric UV, not distorted chart UV.
            max_edge = param.max_edge_m(options.tolerance_m)
            if max_edge is not None:
                su, sv = param.uv_scale()
                scaled = np.column_stack([verts_uv[:, 0] * su, verts_uv[:, 1] * sv,
                                          np.zeros(len(verts_uv))])
                try:
                    scaled, tris = trimesh.remesh.subdivide_to_size(
                        scaled, tris, max_edge=max_edge, max_iter=8)
                except ValueError as exc:
                    if "max_iter exceeded" in str(exc):
                        logger.warning("Subdivision max_iter exceeded for {}: "
                                       "falling back to unsubdivided mesh", part_id)
                    else:
                        raise
                verts_uv = np.column_stack([scaled[:, 0] / su, scaled[:, 1] / sv])
                tris = np.asarray(tris, dtype=np.int64)
            verts3 = param.evaluate(verts_uv)
            if not np.all(np.isfinite(verts3)):
                logger.debug("Non-finite vertices for {}", part_id)
                return None
            tris = _drop_degenerate(verts3, tris)
            if len(tris) == 0:
                continue
            normals = param.normals(verts_uv)
            if reference_normal is not None:
                normals[normals @ reference_normal < 0] *= -1.0
                cross = np.cross(verts3[tris[:, 1]] - verts3[tris[:, 0]],
                                 verts3[tris[:, 2]] - verts3[tris[:, 0]])
                flip = cross @ reference_normal < 0
                tris[flip] = tris[flip, ::-1]
            vert_blocks.append(verts3)
            tri_blocks.append(tris + offset)
            normal_blocks.append(normals)
            offset += len(verts3)
        if not vert_blocks:
            logger.debug("No non-degenerate triangles for {}", part_id)
            return None
        return PartMesh(part_id=part_id, name=name, kind=kind,
                        vertices=np.vstack(vert_blocks), triangles=np.vstack(tri_blocks),
                        normals=np.vstack(normal_blocks))
