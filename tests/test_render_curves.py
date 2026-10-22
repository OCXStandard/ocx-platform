"""Tests for render/curves.py — sampling IR curves to 3D polylines (metres)."""
import numpy as np
from ocx_geometry.curves import sample_contour, sample_curve
from ocx_geometry.measure import LengthResolver
from ocx_model_core.model.ir.base import IrVector3D, Quantity
from ocx_model_core.model.ir.geometry import (
    IrCircle3D,
    IrCircumArc3D,
    IrCompositeCurve3D,
    IrEllipse3D,
    IrLine3D,
    IrNurbs3D,
    IrPoint3D,
    IrPolyLine3D,
)

LR = LengthResolver({})  # empty registry → builtin fallbacks ('Um' → 1.0)


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


class TestSampleCurve:
    def test_line(self):
        c = IrLine3D(curve_length=None, start=pt(0, 0, 0), end=pt(1, 2, 3))
        out = sample_curve(c, LR, tol_m=0.01)
        np.testing.assert_allclose(out, [[0, 0, 0], [1, 2, 3]])

    def test_polyline(self):
        c = IrPolyLine3D(curve_length=None,
                         vertices=[pt(0, 0, 0), pt(1, 0, 0), pt(1, 1, 0)])
        out = sample_curve(c, LR, tol_m=0.01)
        assert out.shape == (3, 3)

    def test_arc_through_three_points_stays_on_circle(self):
        # quarter arc of unit circle in XY plane
        c = IrCircumArc3D(curve_length=None, start=pt(1, 0, 0),
                          intermediate=pt(np.sqrt(0.5), np.sqrt(0.5), 0),
                          end=pt(0, 1, 0))
        out = sample_curve(c, LR, tol_m=0.001)
        assert len(out) >= 8
        radii = np.linalg.norm(out, axis=1)
        np.testing.assert_allclose(radii, 1.0, atol=1e-6)
        np.testing.assert_allclose(out[0], [1, 0, 0], atol=1e-9)
        np.testing.assert_allclose(out[-1], [0, 1, 0], atol=1e-9)

    def test_arc_sagitta_respects_tolerance(self):
        c = IrCircumArc3D(curve_length=None, start=pt(1, 0, 0),
                          intermediate=pt(0, 1, 0), end=pt(-1, 0, 0))
        out = sample_curve(c, LR, tol_m=0.001)
        # chord midpoints must deviate < tol from the unit circle
        mid = 0.5 * (out[:-1] + out[1:])
        sag = 1.0 - np.linalg.norm(mid, axis=1)
        assert np.all(sag < 0.001 + 1e-9)

    def test_collinear_arc_degrades_to_segment(self):
        c = IrCircumArc3D(curve_length=None, start=pt(0, 0, 0),
                          intermediate=pt(1, 0, 0), end=pt(2, 0, 0))
        out = sample_curve(c, LR, tol_m=0.01)
        np.testing.assert_allclose(out[0], [0, 0, 0])
        np.testing.assert_allclose(out[-1], [2, 0, 0])

    def test_full_circle_is_closed_loop(self):
        c = IrCircle3D(curve_length=None, center=pt(0, 0, 5),
                       diameter=Quantity(2.0, "Um"),
                       normal=IrVector3D(0, 0, 1))
        out = sample_curve(c, LR, tol_m=0.001)
        assert len(out) >= 16
        np.testing.assert_allclose(out[0], out[-1], atol=1e-9)
        radii = np.linalg.norm(out - [0, 0, 5], axis=1)
        np.testing.assert_allclose(radii, 1.0, atol=1e-9)

    def test_ellipse(self):
        c = IrEllipse3D(curve_length=None, center=pt(0, 0, 0),
                        major_diameter=Quantity(4.0, "Um"),
                        minor_diameter=Quantity(2.0, "Um"),
                        major_axis=IrVector3D(1, 0, 0),
                        normal=IrVector3D(0, 0, 1))
        out = sample_curve(c, LR, tol_m=0.001)
        # on the ellipse: (x/2)^2 + y^2 == 1
        vals = (out[:, 0] / 2.0) ** 2 + out[:, 1] ** 2
        np.testing.assert_allclose(vals, 1.0, atol=1e-6)

    def test_unsupported_curve_returns_none(self):
        class Weird:
            pass
        assert sample_curve(Weird(), LR, tol_m=0.01) is None

    def test_open_composite_first_segment_is_chain_end(self):
        """First segment's *start* joins the rest: chain must grow at the head."""
        s1 = IrLine3D(None, start=pt(2, 0, 0), end=pt(3, 0, 0))  # chain end
        s2 = IrLine3D(None, start=pt(0, 0, 0), end=pt(1, 0, 0))  # chain start
        s3 = IrLine3D(None, start=pt(1, 0, 0), end=pt(2, 0, 0))  # middle
        c = IrCompositeCurve3D(None, segments=[s1, s2, s3])
        out = sample_curve(c, LR, tol_m=0.01)
        assert out is not None
        np.testing.assert_allclose(out[0], [0, 0, 0], atol=1e-9)
        np.testing.assert_allclose(out[-1], [3, 0, 0], atol=1e-9)


class TestSampleContour:
    def test_composite_stitching_with_reversed_segment(self):
        # square: second segment supplied tip-to-tip reversed
        s1 = IrLine3D(None, start=pt(0, 0, 0), end=pt(1, 0, 0))
        s2 = IrLine3D(None, start=pt(1, 1, 0), end=pt(1, 0, 0))  # reversed
        s3 = IrLine3D(None, start=pt(1, 1, 0), end=pt(0, 1, 0))
        s4 = IrLine3D(None, start=pt(0, 1, 0), end=pt(0, 0, 0))
        c = IrCompositeCurve3D(None, segments=[s1, s2, s3, s4])
        out = sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01)
        assert out is not None
        # closed contour: last point is NOT repeated
        assert not np.allclose(out[0], out[-1])
        assert len(out) == 4

    def test_composite_stitching_with_unordered_segments(self):
        # square supplied out of order: s1, s3, s2, s4
        s1 = IrLine3D(None, start=pt(0, 0, 0), end=pt(1, 0, 0))
        s2 = IrLine3D(None, start=pt(1, 0, 0), end=pt(1, 1, 0))
        s3 = IrLine3D(None, start=pt(1, 1, 0), end=pt(0, 1, 0))
        s4 = IrLine3D(None, start=pt(0, 1, 0), end=pt(0, 0, 0))
        c = IrCompositeCurve3D(None, segments=[s1, s3, s2, s4])
        out = sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01)
        assert out is not None
        assert len(out) == 4

    def test_small_gap_is_snapped(self):
        s1 = IrLine3D(None, start=pt(0, 0, 0), end=pt(1, 0, 0))
        s2 = IrLine3D(None, start=pt(1.005, 0, 0), end=pt(1, 1, 0))
        s3 = IrLine3D(None, start=pt(1, 1, 0), end=pt(0, 0.002, 0))
        c = IrCompositeCurve3D(None, segments=[s1, s2, s3])
        out = sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01)
        assert out is not None
        assert len(out) == 3

    def test_large_gap_returns_none(self):
        s1 = IrLine3D(None, start=pt(0, 0, 0), end=pt(1, 0, 0))
        s2 = IrLine3D(None, start=pt(5, 5, 0), end=pt(0, 1, 0))
        c = IrCompositeCurve3D(None, segments=[s1, s2])
        assert sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01) is None

    def test_open_contour_returns_none(self):
        c = IrPolyLine3D(None, vertices=[pt(0, 0, 0), pt(1, 0, 0), pt(1, 5, 0)])
        assert sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01) is None

    def test_closed_polyline_contour(self):
        c = IrPolyLine3D(None, vertices=[pt(0, 0, 0), pt(1, 0, 0),
                                         pt(1, 1, 0), pt(0, 0, 0)])
        out = sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01)
        assert out is not None
        assert len(out) == 3

    def test_sliver_contour_with_3_points_and_small_gap(self):
        # composite with 3 points that snap-close: [A, B, A']
        # where gap(A, A') <= snap_tol_m
        s1 = IrLine3D(None, start=pt(0, 0, 0), end=pt(1, 0, 0))
        s2 = IrLine3D(None, start=pt(1, 0, 0), end=pt(0, 0.001, 0))
        c = IrCompositeCurve3D(None, segments=[s1, s2])
        # snap_tol_m=0.01 > 0.001 gap, so contour would close with 3 points [A,B,≈A]
        out = sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01)
        # should return None (degenerate sliver after dropping last point)
        assert out is None


class TestCircleEllipseDegenerate:
    def test_circle_with_zero_normal(self):
        c = IrCircle3D(curve_length=None, center=pt(0, 0, 0),
                       diameter=Quantity(2.0, "Um"),
                       normal=IrVector3D(0, 0, 0))
        out = sample_curve(c, LR, tol_m=0.01)
        assert out is None

    def test_ellipse_with_zero_major_axis(self):
        c = IrEllipse3D(curve_length=None, center=pt(0, 0, 0),
                        major_diameter=Quantity(4.0, "Um"),
                        minor_diameter=Quantity(2.0, "Um"),
                        major_axis=IrVector3D(0, 0, 0),
                        normal=IrVector3D(0, 0, 1))
        out = sample_curve(c, LR, tol_m=0.01)
        assert out is None

    def test_ellipse_with_zero_normal(self):
        c = IrEllipse3D(curve_length=None, center=pt(0, 0, 0),
                        major_diameter=Quantity(4.0, "Um"),
                        minor_diameter=Quantity(2.0, "Um"),
                        major_axis=IrVector3D(1, 0, 0),
                        normal=IrVector3D(0, 0, 0))
        out = sample_curve(c, LR, tol_m=0.01)
        assert out is None

    def test_ellipse_with_major_axis_parallel_to_normal(self):
        # major_axis parallel to normal → e2 = cross(n, e1) ≈ 0
        c = IrEllipse3D(curve_length=None, center=pt(0, 0, 0),
                        major_diameter=Quantity(4.0, "Um"),
                        minor_diameter=Quantity(2.0, "Um"),
                        major_axis=IrVector3D(0, 0, 1),
                        normal=IrVector3D(0, 0, 1))
        out = sample_curve(c, LR, tol_m=0.01)
        assert out is None


class TestBadNurbs:
    """ISSUE 1: bad NURBS data should return None, not raise GeomdlException."""

    def test_bad_nurbs_insufficient_control_points(self):
        """degree=3 requires at least 4 control points."""
        bad = IrNurbs3D(
            None, degree=3, control_points=[pt(0, 0, 0), pt(1, 0, 0)],
            knot_vector=[0, 0, 0, 0, 1, 1, 1, 1]
        )
        result = sample_curve(bad, LR, tol_m=0.01)
        assert result is None

    def test_bad_nurbs_inconsistent_knot_vector(self):
        """Knot vector length must equal degree + num_ctrlpts + 1."""
        bad = IrNurbs3D(
            None, degree=2, control_points=[pt(0, 0, 0), pt(1, 0, 0), pt(2, 0, 0)],
            knot_vector=[0, 0, 0, 0, 1, 1]  # too short
        )
        result = sample_curve(bad, LR, tol_m=0.01)
        assert result is None


class TestNurbsCornerSampling:

    def test_bezier_segmented_corners_are_sampled_exactly(self):
        """A rectangle encoded as one closed cubic NURBS (full-multiplicity
        interior knots at the corners, as exported by CAD) must include the
        exact corner points in the sampled polyline; uniform seeding cuts
        the corners by up to the sag tolerance, which chamfers every plate
        corner and opens visible holes where plates meet."""
        corners = np.array([[0.0, 0.0, 0.0], [18.0, 0.0, 0.0],
                            [18.0, 4.4, 0.0], [0.0, 4.4, 0.0]])
        cps = []
        for i, a in enumerate(corners):
            b = corners[(i + 1) % 4]
            cps += [a, a + (b - a) / 3.0, a + 2.0 * (b - a) / 3.0]
        cps.append(corners[0])
        knots = [0.0] * 4 + [1.7] * 3 + [2.3] * 3 + [3.9] * 3 + [5.1] * 4
        c = IrNurbs3D(
            None, degree=3,
            control_points=[pt(*q) for q in cps],
            knot_vector=knots)
        out = sample_curve(c, LR, tol_m=0.05)
        assert out is not None
        for q in corners:
            gap = float(np.linalg.norm(out - q, axis=1).min())
            assert gap < 1e-6, f"corner {q[:2]} missed by {gap:.3f} m"
