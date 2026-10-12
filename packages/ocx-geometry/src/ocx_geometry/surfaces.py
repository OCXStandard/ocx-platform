"""Surface parametrizations: evaluate(u,v), inverse(points), normals.

Each ``SurfaceParam``:
- ``evaluate(uv)``   — (N,2) → (N,3) metres
- ``normals(uv)``    — (N,2) → (N,3) unit normals (numeric by default)
- ``inverse(pts)``   — (N,3) → (N,2); for periodic-u surfaces the u values of
  a *polyline* are unwrapped continuously, so a contour crossing the seam
  stays a single connected run in UV space.
- ``uv_scale()``     — (su, sv) metres per uv unit, for metric subdivision
- ``max_edge_m(tol)``— max metric-UV edge length keeping chordal error <= tol,
  or None when no interior subdivision is needed (planes, ruled directions).
``make_param`` builds the right param from an IrSurface3D, or returns None.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod

import numpy as np
from geomdl.exceptions import GeomdlException
from loguru import logger
from ocx_model_core.model.ir.geometry import (
    IrCone3D,
    IrCylinder3D,
    IrExtrudedSurface,
    IrNurbsSurface,
    IrPlane3D,
    IrSphere3D,
)

from ocx_geometry.curves import _any_perp, _unit, sample_curve
from ocx_geometry.measure import LengthResolver


def _vec(v) -> np.ndarray:
    return np.array([v.x, v.y, v.z], dtype=np.float64)


class SurfaceParam(ABC):
    periodic_u: bool = False

    @abstractmethod
    def evaluate(self, uv: np.ndarray) -> np.ndarray: ...

    @abstractmethod
    def inverse(self, pts: np.ndarray) -> np.ndarray: ...

    def normals(self, uv: np.ndarray) -> np.ndarray:
        """Numeric normals via central differences (overridden where analytic)."""
        uv = np.asarray(uv, dtype=float)
        span = max(float(np.ptp(uv[:, 0])), float(np.ptp(uv[:, 1])), 1.0)
        eps = 1e-5 * span
        du = self.evaluate(uv + [eps, 0.0]) - self.evaluate(uv - [eps, 0.0])
        dv = self.evaluate(uv + [0.0, eps]) - self.evaluate(uv - [0.0, eps])
        n = np.cross(du, dv)
        norms = np.linalg.norm(n, axis=1, keepdims=True)
        norms[norms < 1e-15] = 1.0
        return n / norms

    def uv_scale(self) -> tuple[float, float]:
        return (1.0, 1.0)

    def max_edge_m(self, tol_m: float) -> float | None:
        return None


def _chord_edge(radius: float, tol_m: float) -> float:
    """Max chord length with sagitta <= tol on a circle of given radius."""
    return math.sqrt(max(8.0 * tol_m * radius, 1e-12))


class PlaneParam(SurfaceParam):
    def __init__(self, origin: np.ndarray, normal: np.ndarray,
                 udir: np.ndarray | None = None) -> None:
        self.o = origin
        self.n = _unit(normal)
        if udir is not None and np.linalg.norm(udir) > 1e-12:
            u = udir - (udir @ self.n) * self.n
            self.u = _unit(u) if np.linalg.norm(u) > 1e-12 else _any_perp(self.n)
        else:
            self.u = _any_perp(self.n)
        self.v = np.cross(self.n, self.u)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        return self.o + np.outer(uv[:, 0], self.u) + np.outer(uv[:, 1], self.v)

    def inverse(self, pts):
        d = np.asarray(pts, dtype=float) - self.o
        return np.column_stack([d @ self.u, d @ self.v])

    def normals(self, uv):
        return np.tile(self.n, (len(np.asarray(uv)), 1))


class CylinderParam(SurfaceParam):
    periodic_u = True

    def __init__(self, origin: np.ndarray, axis: np.ndarray, radius: float) -> None:
        self.o, self.a, self.r = origin, _unit(axis), radius
        self.x = _any_perp(self.a)
        self.y = np.cross(self.a, self.x)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        u, v = uv[:, 0], uv[:, 1]
        return (self.o
                + self.r * (np.outer(np.cos(u), self.x) + np.outer(np.sin(u), self.y))
                + np.outer(v, self.a))

    def inverse(self, pts):
        d = np.asarray(pts, dtype=float) - self.o
        v = d @ self.a
        rad = d - np.outer(v, self.a)
        u = np.arctan2(rad @ self.y, rad @ self.x)
        return np.column_stack([np.unwrap(u), v])

    def normals(self, uv):
        u = np.asarray(uv, dtype=float)[:, 0]
        return np.outer(np.cos(u), self.x) + np.outer(np.sin(u), self.y)

    def uv_scale(self):
        return (self.r, 1.0)

    def max_edge_m(self, tol_m):
        return _chord_edge(self.r, tol_m)


class ConeParam(SurfaceParam):
    """v = metres along the axis from the base origin; radius interpolates
    base_radius → tip_radius over the origin→tip height."""
    periodic_u = True

    def __init__(self, origin: np.ndarray, tip: np.ndarray,
                 base_radius: float, tip_radius: float) -> None:
        self.o = origin
        axis = tip - origin
        self.h = float(np.linalg.norm(axis))
        self.a = _unit(axis)
        self.rb, self.rt = base_radius, tip_radius
        self.x = _any_perp(self.a)
        self.y = np.cross(self.a, self.x)

    def _radius(self, v):
        return self.rb + (self.rt - self.rb) * (v / self.h)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        u, v = uv[:, 0], uv[:, 1]
        r = self._radius(v)
        return (self.o
                + (r[:, None] * (np.outer(np.cos(u), self.x)
                                 + np.outer(np.sin(u), self.y)))
                + np.outer(v, self.a))

    def inverse(self, pts):
        d = np.asarray(pts, dtype=float) - self.o
        v = d @ self.a
        rad = d - np.outer(v, self.a)
        u = np.arctan2(rad @ self.y, rad @ self.x)
        return np.column_stack([np.unwrap(u), v])

    def uv_scale(self):
        return (max(self.rb, self.rt), 1.0)

    def max_edge_m(self, tol_m):
        return _chord_edge(max(self.rb, self.rt), tol_m)


class SphereParam(SurfaceParam):
    """u = azimuth (periodic), v = polar angle from the frame z axis."""
    periodic_u = True

    def __init__(self, origin: np.ndarray, radius: float,
                 zdir: np.ndarray | None = None) -> None:
        self.o, self.r = origin, radius
        self.z = _unit(zdir) if zdir is not None and np.linalg.norm(zdir) > 1e-12 \
            else np.array([0.0, 0.0, 1.0])
        self.x = _any_perp(self.z)
        self.y = np.cross(self.z, self.x)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        u, v = uv[:, 0], uv[:, 1]
        return self.o + self.r * (np.outer(np.sin(v) * np.cos(u), self.x)
                                  + np.outer(np.sin(v) * np.sin(u), self.y)
                                  + np.outer(np.cos(v), self.z))

    def inverse(self, pts):
        d = (np.asarray(pts, dtype=float) - self.o) / self.r
        v = np.arccos(np.clip(d @ self.z, -1.0, 1.0))
        u = np.arctan2(d @ self.y, d @ self.x)
        # poles: u is undefined where sin(v) ~ 0 — reuse the neighbour's u
        tiny = np.sin(v) < 1e-9
        for i in np.where(tiny)[0]:
            u[i] = u[i - 1] if i > 0 else 0.0
        return np.column_stack([np.unwrap(u), v])

    def normals(self, uv):
        p = self.evaluate(uv)
        return (p - self.o) / self.r

    def uv_scale(self):
        return (self.r, self.r)

    def max_edge_m(self, tol_m):
        return _chord_edge(self.r, tol_m)


def make_param(surface, length: LengthResolver,
               tol_m: float) -> SurfaceParam | None:
    """Build the parametrization for an IrSurface3D, or None if unsupported
    or missing required fields.  Extended in Task 4 with extruded + NURBS."""
    try:
        if isinstance(surface, IrPlane3D):
            if surface.point_on_surface is None or surface.normal is None:
                return None
            udir = _vec(surface.udirection) if surface.udirection else None
            return PlaneParam(length.point(surface.point_on_surface),
                              _vec(surface.normal), udir)

        if isinstance(surface, IrCylinder3D):
            if surface.origin is None or surface.axis is None or surface.radius is None:
                return None
            radius = length.qty(surface.radius)
            if radius <= 0:
                logger.debug("Cylinder radius must be positive, got {}", radius)
                return None
            return CylinderParam(length.point(surface.origin),
                                 _vec(surface.axis), radius)

        if isinstance(surface, IrCone3D):
            if (surface.origin is None or surface.tip is None
                    or surface.base_radius is None or surface.tip_radius is None):
                return None
            base_radius = length.qty(surface.base_radius)
            tip_radius = length.qty(surface.tip_radius)
            if base_radius <= 0 and tip_radius <= 0:
                logger.debug("Cone must have at least one positive radius; "
                             "base_radius={}, tip_radius={}", base_radius, tip_radius)
                return None
            return ConeParam(length.point(surface.origin), length.point(surface.tip),
                             base_radius, tip_radius)

        if isinstance(surface, IrSphere3D):
            if surface.origin is None or surface.radius is None:
                return None
            radius = length.qty(surface.radius)
            if radius <= 0:
                logger.debug("Sphere radius must be positive, got {}", radius)
                return None
            zdir = _vec(surface.normal) if surface.normal else None
            return SphereParam(length.point(surface.origin), radius, zdir)

        if isinstance(surface, (IrExtrudedSurface, IrNurbsSurface)):
            return _make_param_extended(surface, length, tol_m)
    except (ValueError, ZeroDivisionError, IndexError, GeomdlException) as exc:
        logger.debug("Surface parametrization failed for {}: {}",
                     type(surface).__name__, exc)
        return None
    logger.debug("Unsupported surface type: {}", type(surface).__name__)
    return None


class ExtrudedParam(SurfaceParam):
    """u = arclength along the sampled base curve; v = metres along sweep."""

    def __init__(self, base_pts: np.ndarray, sweep: np.ndarray) -> None:
        self.b = base_pts
        seg = np.linalg.norm(np.diff(base_pts, axis=0), axis=1)
        self.s = np.concatenate([[0.0], np.cumsum(seg)])
        self.d = _unit(sweep)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        base = np.column_stack(
            [np.interp(uv[:, 0], self.s, self.b[:, k]) for k in range(3)])
        return base + np.outer(uv[:, 1], self.d)

    def inverse(self, pts):
        # project out the sweep direction, then do 2D point-to-segment projection
        def flat(x):
            return x - np.outer(x @ self.d, self.d)

        bp = flat(self.b)
        out = np.empty((len(pts), 2))
        for i, p in enumerate(np.asarray(pts, dtype=float)):
            pp = p - (p @ self.d) * self.d
            best_res, best_u = np.inf, 0.0
            for j in range(len(bp) - 1):
                e = bp[j + 1] - bp[j]
                ll = e @ e
                t = 0.0 if ll < 1e-18 else float(np.clip((pp - bp[j]) @ e / ll, 0.0, 1.0))
                res = float(np.linalg.norm(pp - (bp[j] + t * e)))
                if res < best_res:
                    best_res = res
                    best_u = self.s[j] + t * (self.s[j + 1] - self.s[j])
            base = np.array([np.interp(best_u, self.s, self.b[:, k]) for k in range(3)])
            out[i] = (best_u, (p - base) @ self.d)
        return out

    def max_edge_m(self, tol_m):
        """Bound edges by the smallest circumradius along the base polyline."""
        if len(self.b) < 3:
            return None
        p0, p1, p2 = self.b[:-2], self.b[1:-1], self.b[2:]
        a = np.linalg.norm(p1 - p0, axis=1)
        b = np.linalg.norm(p2 - p1, axis=1)
        c = np.linalg.norm(p2 - p0, axis=1)
        area2 = np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)  # 2*area
        with np.errstate(divide="ignore", invalid="ignore"):
            radii = a * b * c / (2.0 * area2)
        radii = radii[np.isfinite(radii) & (area2 > 1e-12 * a * c)]
        if len(radii) == 0:
            return None
        return _chord_edge(float(radii.min()), tol_m)


class NurbsSurfaceParam(SurfaceParam):
    """geomdl-backed B-spline surface with Newton point inversion."""

    _GRID = 16          # seed grid resolution per direction
    _NEWTON_ITERS = 25

    def __init__(self, surface: IrNurbsSurface, length: LengthResolver) -> None:
        from geomdl import BSpline
        s = BSpline.Surface()
        s.degree_u = surface.u_degree
        s.degree_v = surface.v_degree
        s.ctrlpts2d = [[list(length.point(p)) for p in row]
                       for row in surface.control_points]
        s.knotvector_u = list(surface.u_knot_vector)
        s.knotvector_v = list(surface.v_knot_vector)
        self.s = s
        ku, kv = s.knotvector_u, s.knotvector_v
        self.du = (ku[s.degree_u], ku[-s.degree_u - 1])
        self.dv = (kv[s.degree_v], kv[-s.degree_v - 1])
        # seed grid for inversion
        us = np.linspace(*self.du, self._GRID)
        vs = np.linspace(*self.dv, self._GRID)
        grid_uv = np.array([(u, v) for u in us for v in vs])
        self._grid_uv = grid_uv
        self._grid_pts = np.array(
            self.s.evaluate_list([tuple(x) for x in grid_uv]))

    def evaluate(self, uv):
        uv = np.clip(np.asarray(uv, dtype=float),
                     [self.du[0], self.dv[0]], [self.du[1], self.dv[1]])
        return np.array(self.s.evaluate_list([tuple(x) for x in uv]))

    def _invert_one(self, p: np.ndarray) -> tuple[float, float]:
        i = int(np.argmin(np.linalg.norm(self._grid_pts - p, axis=1)))
        u, v = self._grid_uv[i]
        for _ in range(self._NEWTON_ITERS):
            d = self.s.derivatives(float(u), float(v), order=1)
            S = np.array(d[0][0])
            Su, Sv = np.array(d[1][0]), np.array(d[0][1])
            r = S - p
            A = np.array([[Su @ Su, Su @ Sv], [Su @ Sv, Sv @ Sv]])
            b = -np.array([Su @ r, Sv @ r])
            try:
                step = np.linalg.solve(A, b)
            except np.linalg.LinAlgError:
                break
            u = float(np.clip(u + step[0], *self.du))
            v = float(np.clip(v + step[1], *self.dv))
            if abs(step[0]) * np.linalg.norm(Su) \
                    + abs(step[1]) * np.linalg.norm(Sv) < 1e-9:
                break
        return u, v

    def inverse(self, pts):
        return np.array([self._invert_one(p)
                         for p in np.asarray(pts, dtype=float)])

    def uv_scale(self):
        uc = 0.5 * (self.du[0] + self.du[1])
        vc = 0.5 * (self.dv[0] + self.dv[1])
        d = self.s.derivatives(uc, vc, order=1)
        su = float(np.linalg.norm(d[1][0]))
        sv = float(np.linalg.norm(d[0][1]))
        return (max(su, 1e-9), max(sv, 1e-9))

    def max_edge_m(self, tol_m):
        """Estimate min curvature radius from 2nd derivatives on a 3x3 grid."""
        kappa_max = 0.0
        for u in np.linspace(*self.du, 3):
            for v in np.linspace(*self.dv, 3):
                d = self.s.derivatives(float(u), float(v), order=2)
                Su, Sv = np.array(d[1][0]), np.array(d[0][1])
                n = np.cross(Su, Sv)
                nn = np.linalg.norm(n)
                if nn < 1e-12:
                    continue
                n = n / nn
                for second, first in ((d[2][0], Su), (d[0][2], Sv)):
                    denom = np.linalg.norm(first) ** 2
                    if denom > 1e-12:
                        kappa_max = max(kappa_max,
                                        abs(np.array(second) @ n) / denom)
        if kappa_max < 1e-9:
            return None
        return _chord_edge(1.0 / kappa_max, tol_m)


def _make_param_extended(surface, length: LengthResolver,
                         tol_m: float) -> SurfaceParam | None:
    if isinstance(surface, IrExtrudedSurface):
        if surface.base_curve is None or surface.sweep is None:
            return None
        base = sample_curve(surface.base_curve, length, tol_m)
        if base is None or len(base) < 2:
            return None
        return ExtrudedParam(base, _vec(surface.sweep))

    if isinstance(surface, IrNurbsSurface):
        if (surface.u_degree is None or surface.v_degree is None
                or not surface.u_knot_vector or not surface.v_knot_vector
                or not surface.control_points):
            return None
        return NurbsSurfaceParam(surface, length)
    return None


def _member_fit(member: SurfaceParam, pts: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """(uv, round-trip points, residuals) of ``pts`` on ``member``."""
    try:
        uv = np.asarray(member.inverse(pts), dtype=float)
        q = np.asarray(member.evaluate(uv), dtype=float)
    except Exception:  # noqa: BLE001 — member disqualifies itself
        return None
    if not (np.isfinite(uv).all() and np.isfinite(q).all()):
        return None
    return uv, q, np.linalg.norm(q - pts, axis=1)


class CompositeParam(SurfaceParam):
    """Developed (girth, spine) chart over an ordered set of member surfaces.

    Built from the plate contour: each contour point is assigned to the
    member fitting it best; the chart coordinate ``u`` is the cumulative
    transverse (girth) arc length along the contour and ``v`` the coordinate
    along the spine axis.  Each member gets an affine map between its own
    UV and the (girth, spine) chart, fitted on its assigned contour points —
    exact for developable members (planes, cylinders), approximate otherwise.
    """

    _SEAM_PAD = 1e-6

    def __init__(self, members: list[SurfaceParam], contour: np.ndarray) -> None:
        contour = np.asarray(contour, dtype=float)
        fits = [_member_fit(m, contour) for m in members]
        ok = [i for i, f in enumerate(fits) if f is not None]
        if len(ok) < 2:
            raise ValueError("composite needs >= 2 fitting members")
        res = np.full((len(members), len(contour)), np.inf)
        for i in ok:
            res[i] = fits[i][2]
        assign = np.argmin(res, axis=0)
        # points fitting several members near-equally (seams) belong to all
        min_res = res[assign, np.arange(len(contour))]
        shared = res <= min_res + 1e-9

        # spine = direction most orthogonal to all member normals
        normals = []
        for i in ok:
            idx = np.nonzero(assign == i)[0]
            if len(idx):
                normals.append(np.asarray(members[i].normals(fits[i][0][idx]),
                                          dtype=float))
        nn = np.vstack(normals)
        _, _, vt = np.linalg.svd(nn, full_matrices=True)
        self.spine = vt[-1]

        # cumulative signed transverse (girth) arc length along the contour.
        # The sign must be intrinsic to the surface: project each step onto
        # the transverse tangent t = spine x normal (normals made
        # sign-continuous along the contour).  Comparing against the previous
        # step direction folds the development when the transverse direction
        # rotates past 90 degrees on curved hulls.
        n = np.zeros((len(contour), 3))
        for i in ok:
            idx = np.nonzero(assign == i)[0]
            if len(idx):
                n[idx] = np.asarray(members[i].normals(fits[i][0][idx]),
                                    dtype=float)
        for j in range(1, len(contour)):
            if n[j] @ n[j - 1] < 0.0:
                n[j] = -n[j]
        t = np.cross(self.spine, n)
        t_norm = np.linalg.norm(t, axis=1)
        for j in range(len(contour)):
            if t_norm[j] > 1e-12:
                t[j] /= t_norm[j]
            elif j > 0:
                t[j] = t[j - 1]
        g = np.zeros(len(contour))
        for j in range(1, len(contour)):
            step = contour[j] - contour[j - 1]
            tr = step - (step @ self.spine) * self.spine
            g[j] = g[j - 1] + tr @ (0.5 * (t[j] + t[j - 1]))
        v = contour @ self.spine

        # per-member affine chart uv_k -> (g, v) and its inverse
        self.members: list[SurfaceParam] = []
        self.affine: list[np.ndarray] = []       # 3x2: [u, v, 1] @ A = (g, v)
        self.inv_affine: list[np.ndarray] = []
        self.g_range: list[tuple[float, float]] = []
        self.v_range: list[tuple[float, float]] = []
        for i in ok:
            idx = np.nonzero(shared[i])[0]
            if len(idx) < 3:
                continue
            uv = fits[i][0][idx]
            basis = np.column_stack([uv, np.ones(len(idx))])
            a, *_ = np.linalg.lstsq(basis, np.column_stack([g[idx], v[idx]]),
                                    rcond=None)
            lin = a[:2]
            if abs(np.linalg.det(lin)) < 1e-12:
                continue
            fit_err = float(np.abs(basis @ a
                                   - np.column_stack([g[idx], v[idx]])).max())
            if fit_err > 0.05 * max(1.0, float(np.ptp(g))):
                continue                          # chart not developable enough
            self.members.append(members[i])
            self.affine.append(a)
            self.inv_affine.append(np.linalg.inv(lin))
            self.g_range.append((float(g[idx].min()), float(g[idx].max())))
            self.v_range.append((float(v[idx].min()), float(v[idx].max())))
        if len(self.members) < 2:
            raise ValueError("composite chart fit failed")
        # Exact chart correspondence for the construction contour.  Points on
        # patches with too few contour samples to fit an affine chart would
        # otherwise be clamped onto the wrong member by inverse().
        self._src_pts = contour
        self._src_gv = np.column_stack([g, v])

    def _member_for_gv(self, gq: float, vq: float) -> int:
        """Member whose fitted (g, v) box best contains or is nearest (gq, vq).

        Collection members can form a 2-D grid (girth x spine), so several
        members may share a girth range; selection must use both axes.
        """
        best, score = 0, np.inf
        for k, ((glo, ghi), (vlo, vhi)) in enumerate(zip(self.g_range,
                                                         self.v_range)):
            sg = abs(gq - 0.5 * (glo + ghi)) - 0.5 * (ghi - glo)
            sv = abs(vq - 0.5 * (vlo + vhi)) - 0.5 * (vhi - vlo)
            s = max(sg, sv)                       # <=0 inside the box
            if s > self._SEAM_PAD:                # outside: nearest box
                s = max(sg, 0.0) + max(sv, 0.0) + 1e3
            if s < score:
                best, score = k, s
        return best

    def _member_uv(self, uv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        uv = np.atleast_2d(np.asarray(uv, dtype=float))
        ks = np.array([self._member_for_gv(q[0], q[1]) for q in uv])
        out = np.empty_like(uv)
        for k in np.unique(ks):
            sel = ks == k
            a = self.affine[k]
            out[sel] = (uv[sel] - a[2]) @ self.inv_affine[k]
        return ks, out

    def evaluate(self, uv):
        uv = np.atleast_2d(np.asarray(uv, dtype=float))
        ks, muv = self._member_uv(uv)
        out = np.empty((len(muv), 3))
        for k in np.unique(ks):
            sel = ks == k
            out[sel] = self.members[k].evaluate(muv[sel])
        # construction contour points evaluate to their exact 3D positions
        d = np.linalg.norm(uv[:, None, :] - self._src_gv[None], axis=2)
        j = d.argmin(axis=1)
        snap = d[np.arange(len(uv)), j] < 1e-7
        out[snap] = self._src_pts[j[snap]]
        return out

    def inverse(self, pts):
        pts = np.atleast_2d(np.asarray(pts, dtype=float))
        fits = [_member_fit(m, pts) for m in self.members]
        res = np.full((len(self.members), len(pts)), np.inf)
        for k, f in enumerate(fits):
            if f is not None:
                res[k] = f[2]
        ks = np.argmin(res, axis=0)
        out = np.empty((len(pts), 2))
        for k in np.unique(ks):
            sel = ks == k
            uv = fits[k][0][sel]
            out[sel] = np.column_stack([uv, np.ones(len(uv))]) @ self.affine[k]
        # construction contour points map to their exact chart coordinates
        # whenever that beats the member round-trip residual
        d = np.linalg.norm(pts[:, None, :] - self._src_pts[None], axis=2)
        j = d.argmin(axis=1)
        dmin = d[np.arange(len(pts)), j]
        snap = dmin <= np.maximum(res[ks, np.arange(len(pts))], 1e-9)
        out[snap] = self._src_gv[j[snap]]
        return out

    def normals(self, uv):
        ks, muv = self._member_uv(uv)
        out = np.empty((len(muv), 3))
        for k in np.unique(ks):
            sel = ks == k
            out[sel] = self.members[k].normals(muv[sel])
        return out

    def max_edge_m(self, tol_m):
        edges = [e for e in (m.max_edge_m(tol_m) for m in self.members)
                 if e is not None]
        return min(edges) if edges else None


def make_composite(members: list[SurfaceParam],
                   contour: np.ndarray) -> CompositeParam | None:
    """Composite chart over collection members, or None if not fittable."""
    try:
        return CompositeParam(members, contour)
    except (ValueError, np.linalg.LinAlgError) as exc:
        logger.debug("Composite chart failed: {}", exc)
        return None
