"""Write a self-contained three.js HTML viewer next to a GLB file.

The GLB is embedded base64 so the page works when opened via file:// with no
server.  three.js is loaded from a pinned CDN version via an import map.
Placeholders are replaced with str.replace (not str.format) so the template
can contain CSS/JS braces freely.
"""
from __future__ import annotations

import base64
from pathlib import Path

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>__TITLE__</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;font-family:system-ui,sans-serif}
  #tree{position:absolute;top:0;left:0;bottom:0;width:280px;overflow:auto;
        background:#1e1e1ecc;color:#ddd;font-size:12px;padding:8px;box-sizing:border-box}
  #tree div{cursor:pointer;padding:1px 4px;white-space:nowrap}
  #tree div:hover{background:#444}
  #tree div.sel{background:#2a6}
  #info{position:absolute;right:8px;top:8px;background:#1e1e1ecc;color:#ddd;
        font-size:12px;padding:8px;max-width:320px;white-space:pre-wrap}
</style>
<script type="importmap">
{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js",
"three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}
</script>
</head>
<body>
<div id="tree"></div><div id="info"></div>
<script type="module">
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const GLB_B64 = "__GLB_B64__";
const bin = Uint8Array.from(atob(GLB_B64), c => c.charCodeAt(0)).buffer;

const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x202830);
const camera = new THREE.PerspectiveCamera(50, innerWidth/innerHeight, 0.01, 1e6);
const controls = new OrbitControls(camera, renderer.domElement);
scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.2));
const dir = new THREE.DirectionalLight(0xffffff, 1.5);
dir.position.set(1, 2, 3);
scene.add(dir);

const tree = document.getElementById('tree');
const info = document.getElementById('info');
let selected = null;

new GLTFLoader().parse(bin, '', (gltf) => {
  scene.add(gltf.scene);
  const box = new THREE.Box3().setFromObject(gltf.scene);
  const c = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length() || 10;
  camera.position.copy(c).add(new THREE.Vector3(size*0.6, size*0.4, size*0.6));
  controls.target.copy(c);
  gltf.scene.traverse(o => {
    if (!o.isMesh) return;
    const row = document.createElement('div');
    row.textContent = o.name || '(unnamed)';
    row.onclick = () => select(o, row);
    tree.appendChild(row);
  });
}, (err) => { info.textContent = 'Failed to load model: ' + err; });

function select(obj, row) {
  if (selected) {
    if (selected.obj.material.emissive) selected.obj.material.emissive.setHex(0x000000);
    selected.row.classList.remove('sel');
  }
  obj.material = obj.material.clone();
  if (obj.material.emissive) obj.material.emissive.setHex(0x22aa55);
  row.classList.add('sel');
  selected = {obj, row};
  info.textContent = obj.name + "\\n" + JSON.stringify(obj.userData, null, 1);
}

addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
(function loop() { requestAnimationFrame(loop); controls.update(); renderer.render(scene, camera); })();
</script>
</body>
</html>
"""


def write_html(glb_path: Path, destination: Path | None = None) -> Path:
    """Write ``<glb stem>.html`` (or ``destination``) with the GLB embedded."""
    glb_path = Path(glb_path)
    destination = destination or glb_path.with_suffix(".html")
    b64 = base64.b64encode(glb_path.read_bytes()).decode("ascii")
    html = _TEMPLATE.replace("__TITLE__", glb_path.stem).replace("__GLB_B64__", b64)
    destination.write_text(html, encoding="utf-8")
    return destination
