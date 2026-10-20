# Changelog — ocx-render

## 0.1.0 — 2026-10-20

Initial release.

### Added

- `render_model(vessel, options) → RenderResult`: tessellates an IR model
  (plates, stiffeners, brackets, pillars) via `ocx-geometry`.
- GLB writer (`gltf_writer`): writes tessellated meshes to a `.glb` file.
- Self-contained HTML viewer (`html_viewer`) wrapping the GLB.
- `ocx-render` CLI: `ocx-render model.3docx [--destination out.glb]
  [--tolerance MM] [--no-html]` with exit codes 0 (rendered),
  1 (nothing renderable), 2 (cannot parse), 3 (cannot write output).
