# ocx-render

Tessellates OCX `.3docx` models (via the schema-neutral IR from `ocx-model-core`
and the geometry kernel in `ocx-geometry`) into a GLB file plus a self-contained
three.js HTML viewer.

    ocx-render model.3docx [--destination out.glb] [--tolerance MM] [--no-html]

Exit codes: 0 rendered (parts may be skipped), 1 nothing renderable,
2 cannot parse/build the model.
