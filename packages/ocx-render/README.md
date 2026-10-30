# ocx-render

Tessellates OCX `.3docx` models (via the schema-neutral IR from `ocx-model-core`
and the geometry kernel in `ocx-geometry`) into a GLB file plus a self-contained
three.js HTML viewer.

Geometry stays in OCX Z-up coordinates internally. GLB export rotates positions
and normals to glTF's right-handed Y-up convention: `(x, y, z)` becomes
`(x, z, -y)`. The HTML viewer uses these same exported coordinates.

    ocx-render model.3docx [--destination out.glb] [--tolerance MM] [--no-html]

The HTML viewer embeds the GLB, so it opens straight from disk, but it
loads three.js from unpkg.com and therefore needs network access; offline it
shows an explanatory message instead of the model. Its side panel lists parts
grouped by panel, with a filter box (matches name, id, guid, panel id and
function type) and show/hide checkboxes; clicking a part in the tree or in
the 3D view selects it and shows its metadata.

Exit codes: 0 rendered (parts may be skipped), 1 nothing renderable,
2 cannot parse/build the model, 3 cannot write output.
