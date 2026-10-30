"""Write a self-contained three.js HTML viewer next to a GLB file.

The GLB is embedded base64 so the page works when opened via file:// with no
server.  three.js is loaded from a pinned CDN version via an import map, so
the page needs network access; if the CDN cannot be reached the page says so.
Placeholders are substituted in a single pass (not str.format) so the
template can contain CSS/JS braces freely.
"""
from __future__ import annotations

import base64
import html
import re
from pathlib import Path

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>__TITLE__</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;font-family:system-ui,sans-serif}
  #side{position:absolute;top:0;left:0;bottom:0;width:280px;display:flex;
        flex-direction:column;background:#1e1e1ecc;color:#ddd;font-size:12px}
  #search{margin:8px;padding:4px 6px;background:#111;color:#ddd;
          border:1px solid #555;font:inherit}
  #tree,#results{flex:1;overflow:auto;padding:0 8px 8px}
  #side summary{cursor:pointer;white-space:nowrap;padding:1px 0}
  #side .row{cursor:pointer;padding:1px 4px;white-space:nowrap}
  #side details>.row{padding-left:18px}
  #side .row:hover{background:#444}
  #side .row.sel{background:#2a6}
  #side input[type=checkbox]{margin:0 4px 0 0;vertical-align:middle}
  #info{position:absolute;right:8px;top:8px;background:#1e1e1ecc;color:#ddd;
        font-size:12px;padding:8px;max-width:320px;white-space:pre-wrap}
  #info:empty{display:none}
  #status{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
          color:#ddd;font-size:14px;max-width:60%;text-align:center}
</style>
<script type="importmap">
{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js",
"three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}
</script>
</head>
<body>
<div id="side">
  <input id="search" type="search" placeholder="Filter parts (name, id, guid, panel)"/>
  <div id="tree"></div><div id="results" hidden></div>
</div>
<div id="info"></div>
<div id="status">Loading model&hellip;</div>
<script>
function viewerFailed(msg) {
  document.getElementById('status').textContent = msg;
  document.body.dataset.state = 'error';
}
</script>
<script type="module" onerror="viewerFailed('Could not load three.js from unpkg.com: the viewer needs network access.')">
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const GLB_B64 = "__GLB_B64__";
const HIGHLIGHT = 0x22aa55;
const MAX_RESULTS = 500;

const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setSize(innerWidth, innerHeight);
document.body.prepend(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x202830);
const camera = new THREE.PerspectiveCamera(50, innerWidth/innerHeight, 0.01, 1000);
const controls = new OrbitControls(camera, renderer.domElement);
scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.2));
const dir = new THREE.DirectionalLight(0xffffff, 1.5);
dir.position.set(1, 2, 3);
scene.add(dir);

const tree = document.getElementById('tree');
const results = document.getElementById('results');
const search = document.getElementById('search');
const info = document.getElementById('info');

let modelSize = 10;
const parts = [];               // every mesh, in tree order
const haystack = new Map();     // mesh -> lower-case search text
const rowOf = new Map();        // mesh -> its tree row (once created)
const groupOf = new Map();      // mesh -> enclosing <details>
let selected = null;            // {obj, original}

// A data: URL fetch decodes base64 natively: far faster and leaner than
// base64-decoding in JS with a per-byte copy on large models.
fetch('data:model/gltf-binary;base64,' + GLB_B64)
  .then(r => r.arrayBuffer())
  .then(bin => new GLTFLoader().parseAsync(bin, ''))
  .then(onLoad)
  .catch(err => viewerFailed('Failed to load model: ' + err));

function onLoad(gltf) {
  scene.add(gltf.scene);
  const box = new THREE.Box3().setFromObject(gltf.scene);
  const c = box.getCenter(new THREE.Vector3());
  modelSize = box.getSize(new THREE.Vector3()).length() || 10;
  camera.position.copy(c).add(new THREE.Vector3(modelSize*0.6, modelSize*0.4, modelSize*0.6));
  controls.target.copy(c);
  for (const child of gltf.scene.children) {
    tree.appendChild(child.isMesh ? partRow(child) : groupNode(child));
  }
  document.getElementById('status').remove();
  document.body.dataset.state = 'loaded';
}

function register(obj) {
  parts.push(obj);
  haystack.set(obj, [obj.name, ...Object.values(obj.userData)].join(' ').toLowerCase());
}

function groupNode(group) {
  const members = [];
  group.traverse(o => { if (o.isMesh) members.push(o); });
  const det = document.createElement('details');
  const sum = document.createElement('summary');
  sum.append(visibilityBox(group), `${group.name || '(group)'} (${members.length})`);
  det.append(sum);
  for (const o of members) { register(o); groupOf.set(o, det); }
  // Rows are created on first open so models with thousands of parts stay cheap.
  det.fill = () => {
    if (det.filled) return;
    det.filled = true;
    for (const o of members) det.append(partRow(o, false));
  };
  det.addEventListener('toggle', () => { if (det.open) det.fill(); });
  return det;
}

function partRow(obj, isNew = true) {
  if (isNew) register(obj);
  const row = makeRow(obj);
  rowOf.set(obj, row);
  return row;
}

function makeRow(obj) {
  const row = document.createElement('div');
  row.className = 'row';
  row.append(visibilityBox(obj), obj.name || '(unnamed)');
  row.onclick = () => select(obj);
  return row;
}

function visibilityBox(obj) {
  const box = document.createElement('input');
  box.type = 'checkbox';
  box.checked = obj.visible;
  box.title = 'Show / hide';
  box.onclick = e => e.stopPropagation();
  box.onchange = () => {
    obj.visible = box.checked;
    for (const other of document.querySelectorAll('#side input[type=checkbox]')) {
      if (other !== box && other.target === obj) other.checked = box.checked;
    }
  };
  box.target = obj;
  return box;
}

search.addEventListener('input', () => {
  const q = search.value.trim().toLowerCase();
  tree.hidden = q !== '';
  results.hidden = q === '';
  results.replaceChildren();
  if (!q) return;
  const hits = parts.filter(o => haystack.get(o).includes(q));
  for (const o of hits.slice(0, MAX_RESULTS)) results.append(makeRow(o));
  if (hits.length > MAX_RESULTS) {
    const more = document.createElement('div');
    more.textContent = `… ${hits.length - MAX_RESULTS} more, refine the filter`;
    results.append(more);
  }
});

function select(obj) {
  if (selected) {
    selected.obj.material.dispose();
    selected.obj.material = selected.original;
    rowOf.get(selected.obj)?.classList.remove('sel');
    selected = null;
  }
  info.textContent = '';
  if (!obj) return;
  // Highlight a private clone so parts sharing the material stay unlit;
  // the clone is disposed and the original restored on deselect.
  const original = obj.material;
  obj.material = original.clone();
  if (obj.material.emissive) obj.material.emissive.setHex(HIGHLIGHT);
  selected = {obj, original};
  info.textContent = obj.name + '\\n' + JSON.stringify(obj.userData, null, 1);
  const det = groupOf.get(obj);
  if (det) { det.fill(); det.open = true; }
  const row = rowOf.get(obj);
  if (row) { row.classList.add('sel'); row.scrollIntoView({block: 'nearest'}); }
}

function shown(obj) {
  for (let o = obj; o; o = o.parent) if (!o.visible) return false;
  return true;
}

// Click (not drag) in the 3D view picks the nearest visible part.
const raycaster = new THREE.Raycaster();
let down = null;
renderer.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', e => {
  if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
  const ndc = new THREE.Vector2(e.clientX / innerWidth * 2 - 1,
                                -(e.clientY / innerHeight) * 2 + 1);
  raycaster.setFromCamera(ndc, camera);
  const hit = raycaster.intersectObjects(parts, false).find(h => shown(h.object));
  select(hit ? hit.object : null);
});

addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
(function loop() {
  requestAnimationFrame(loop);
  controls.update();
  // Depth range follows the view distance: a fixed huge far/near ratio
  // z-fights on ship-sized models, a fixed small one clips them.
  const dist = camera.position.distanceTo(controls.target);
  camera.near = Math.max(dist / 1000, modelSize / 1e6);
  camera.far = dist + modelSize * 2;
  camera.updateProjectionMatrix();
  renderer.render(scene, camera);
})();
</script>
</body>
</html>
"""


def write_html(glb_path: Path, destination: Path | None = None) -> Path:
    """Write ``<glb stem>.html`` (or ``destination``) with the GLB embedded."""
    glb_path = Path(glb_path)
    destination = destination or glb_path.with_suffix(".html")
    values = {
        "TITLE": html.escape(glb_path.stem),
        "GLB_B64": base64.b64encode(glb_path.read_bytes()).decode("ascii"),
    }
    page = re.sub(r"__(TITLE|GLB_B64)__", lambda m: values[m.group(1)],
                  _TEMPLATE)
    destination.write_text(page, encoding="utf-8")
    return destination
