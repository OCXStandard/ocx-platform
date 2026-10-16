// WebGL viewer for the diagnose report: one mesh per plate, GPU colour-id picking.
(function () {
  let R, S, P, cam, ctl, pickT, host, ready = false, focus = null;
  const meshes = {}, pickMeshes = [], names = [];
  const BG = new THREE.Color(0xf4f6fa), RED = new THREE.Color(0xe00000);

  function b64(s, T) {
    const b = atob(s), u = new Uint8Array(b.length);
    for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);
    return new T(u.buffer);
  }
  function render() { if (ready) R.render(S, cam); }
  function resize() {
    const w = host.clientWidth, h = host.clientHeight;
    if (!w || !h) return;
    R.setSize(w, h);
    cam.aspect = w / h; cam.updateProjectionMatrix();
    pickT.setSize(w, h);
    render();
  }
  function pick(x, y) {
    const w = pickT.width, h = pickT.height, px = new Uint8Array(4);
    R.setRenderTarget(pickT); R.render(P, cam);
    R.readRenderTargetPixels(pickT, Math.min(w - 1, x), Math.max(0, h - 1 - y), 1, 1, px);
    R.setRenderTarget(null);
    const id = (px[0] << 16) | (px[1] << 8) | px[2];
    return id > 0 ? names[id - 1] : null;
  }
  function paint() {
    for (const n in meshes) {
      const m = meshes[n], c = m.userData.col.clone();
      m.material.color.copy(!focus ? c : (n === focus ? RED : c.lerp(BG, 0.65)));
    }
    render();
  }
  window.viewerFocus = function (name, zoom) {
    focus = name || null;
    paint();
    const m = focus && meshes[focus];
    if (m && zoom) {
      const s = m.geometry.boundingSphere, d = cam.position.clone().sub(ctl.target).normalize();
      ctl.target.copy(s.center);
      cam.position.copy(s.center).addScaledVector(d, Math.max(s.radius, 1e-3) * 3);
      ctl.update(); render();
    }
  };
  window.initViewer = function () {
    if (ready) { resize(); return; }
    host = document.getElementById('v3d');
    const data = JSON.parse(document.getElementById('v3dj').textContent);
    R = new THREE.WebGLRenderer({ antialias: true });
    R.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    host.appendChild(R.domElement);
    S = new THREE.Scene(); S.background = BG;
    P = new THREE.Scene(); P.background = new THREE.Color(0x000000);
    cam = new THREE.PerspectiveCamera(40, 1, 0.1, 1e6);
    S.add(cam);
    S.add(new THREE.HemisphereLight(0xffffff, 0x8890a0, 0.8));
    const dl = new THREE.DirectionalLight(0xffffff, 0.7); cam.add(dl);
    pickT = new THREE.WebGLRenderTarget(1, 1);
    const box = new THREE.Box3();
    data.plates.forEach((p, i) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(b64(p.v, Float32Array), 3));
      g.setIndex(new THREE.BufferAttribute(b64(p.f, Uint32Array), 1));
      g.computeVertexNormals(); g.computeBoundingSphere(); g.computeBoundingBox();
      box.union(g.boundingBox);
      const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ color: p.color, side: THREE.DoubleSide }));
      m.userData.col = new THREE.Color(p.color);
      S.add(m); meshes[p.id] = m; names.push(p.id);
      const id = i + 1;
      P.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({
        color: new THREE.Color((id >> 16 & 255) / 255, (id >> 8 & 255) / 255, (id & 255) / 255),
        side: THREE.DoubleSide, toneMapped: false })));
    });
    const sph = box.getBoundingSphere(new THREE.Sphere());
    cam.far = sph.radius * 20; cam.near = sph.radius / 1000;
    cam.position.copy(sph.center).add(new THREE.Vector3(1, -1.2, 0.8).normalize().multiplyScalar(sph.radius * 2.6));
    cam.up.set(0, 0, 1);
    ctl = new THREE.OrbitControls(cam, R.domElement);
    ctl.target.copy(sph.center); ctl.update();
    ctl.addEventListener('change', render);
    let down = null;
    R.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
    R.domElement.addEventListener('pointerup', e => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
      const r = R.domElement.getBoundingClientRect();
      const name = pick(Math.round(e.clientX - r.left), Math.round(e.clientY - r.top));
      if (name) focusPlate(name, false);
    });
    new ResizeObserver(resize).observe(host);
    ready = true;
    resize(); paint();
  };
})();
