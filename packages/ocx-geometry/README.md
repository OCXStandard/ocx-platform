# ocx-geometry

Geometry evaluation kernel for the OCX IR: curve/surface evaluation, length
and area measurement, contour-closure checks and tessellation into plain
numpy mesh arrays. No display or rendering stack.

Multi-patch plates use plate-local LSCM charts. Tangent-plane envelopes include
the bounded NURBS patches' tangent-boundary samples before being clipped
against their projected footprints, preventing sparse plate hints from leaving
artificial seam holes. Chart regions are triangulated face by face in their
source-member UV coordinates. This
preserves patch seams and holes and avoids treating distorted chart UV as a
uniform metric. Chart construction seeds straight contour edges by arc length;
contour roundtrip alone is not a sufficient check of rendered plate interiors.
Authored cut-outs remain excluded from source-face clipping.

Part of the ocx-platform workspace. See the repository root README.
