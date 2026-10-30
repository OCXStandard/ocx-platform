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

Plates on multi-member panels are trimmed out of the panel's shared chart
mesh (`mesh_trim.MeshTrimmer`): the plate contour is walked over the mesh,
crossed faces are split, and the pieces are grouped into connected regions
whose inside/outside side is voted at the contour itself. A trim whose kept
vector area is far above the contour's is rejected so the caller can fall
back to another route (a correct trim's vector area equals the contour's
however curved the surface). Holes are then cut from the trimmed plate;
a hole is only cut when it reaches into the plate's interior, so openings
the plate outline runs around are left alone.

Part of the ocx-platform workspace. See the repository root README.
