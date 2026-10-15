import numpy as np
import shapely
from ocx_geometry.lscm import _facet_trimmed
from ocx_geometry.surfaces import PlaneParam


def _plane():
    return PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))


def test_unsupported_thin_sliver_between_distant_hints_is_dropped():
    # Wide flat part plus a distant keel line: the convex hull spans the
    # gap with a thin strip no plate covers.
    flat = np.array([[-10, -0.4], [0, -0.4], [0, 4], [-10, 4]], float)
    keel = np.array([[30, 0], [40, 0]], float)
    excluded = shapely.box(100, 100, 101, 101)
    _, uv, faces = _facet_trimmed(_plane(), np.vstack([flat, keel]), 0.05,
                                  excluded)
    centroid_u = uv[faces][..., 0].mean(axis=1)
    assert not ((centroid_u > 23.0) & (centroid_u < 27.0)).any()


def test_supported_narrow_region_is_kept():
    strip = np.array([[0, 0], [20, 0], [20, 0.6], [0, 0.6]], float)
    out = _facet_trimmed(_plane(), strip, 0.05)
    assert out is not None and len(out[2]) > 0
