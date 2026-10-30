"""Tests for the self-contained HTML viewer writer."""
import base64
from pathlib import Path

import pytest
from ocx_render.html_viewer import write_html


class TestWriteHtml:
    def test_writes_self_contained_page(self, tmp_path):
        glb = tmp_path / "boat.glb"
        payload = b"glTF-fake-binary-content"
        glb.write_bytes(payload)

        out = write_html(glb)
        assert out == tmp_path / "boat.html"
        html = out.read_text(encoding="utf-8")
        assert "<title>boat</title>" in html
        assert "importmap" in html
        assert "three@0.160.0" in html                     # pinned CDN version
        assert base64.b64encode(payload).decode() in html  # GLB embedded
        assert "__GLB_B64__" not in html                   # placeholder replaced
        assert "__TITLE__" not in html

    def test_explicit_destination(self, tmp_path):
        glb = tmp_path / "boat.glb"
        glb.write_bytes(b"x")
        out = write_html(glb, destination=tmp_path / "custom.html")
        assert out.name == "custom.html" and out.exists()


def _module_script(html: str) -> str:
    start = html.index('<script type="module"')
    start = html.index(">", start) + 1
    return html[start:html.index("</script>", start)]


class TestTemplate:
    def test_title_is_html_escaped(self, tmp_path):
        glb = tmp_path / "a<b&c.glb"
        glb.write_bytes(b"x")
        html = write_html(glb).read_text(encoding="utf-8")
        assert "<title>a&lt;b&amp;c</title>" in html

    def test_placeholder_text_in_title_is_not_substituted(self, tmp_path):
        glb = tmp_path / "__GLB_B64__.glb"
        payload = b"glTF-payload"
        glb.write_bytes(payload)
        html = write_html(glb).read_text(encoding="utf-8")
        assert "<title>__GLB_B64__</title>" in html
        assert html.count(base64.b64encode(payload).decode()) == 1

    def test_glb_decoded_natively_via_data_url(self, tmp_path):
        glb = tmp_path / "m.glb"
        glb.write_bytes(b"x")
        html = write_html(glb).read_text(encoding="utf-8")
        assert "data:model/gltf-binary;base64," in html
        assert "atob(" not in html

    def test_cdn_failure_is_reported_in_page(self, tmp_path):
        glb = tmp_path / "m.glb"
        glb.write_bytes(b"x")
        html = write_html(glb).read_text(encoding="utf-8")
        assert 'id="status"' in html and "onerror=" in html
        assert "needs network access" in html

    def test_module_script_parses(self, tmp_path):
        import shutil
        import subprocess

        node = shutil.which("node")
        if node is None:
            pytest.skip("node not installed")
        glb = tmp_path / "m.glb"
        glb.write_bytes(b"x")
        js = tmp_path / "viewer.mjs"
        js.write_text(_module_script(write_html(glb).read_text(encoding="utf-8")),
                      encoding="utf-8")
        proc = subprocess.run([node, "--check", str(js)], capture_output=True,
                              text=True)
        assert proc.returncode == 0, proc.stderr


_SELFTEST = """
const waitLoaded = setInterval(() => {
  if (document.body.dataset.state !== 'loaded') return;
  clearInterval(waitLoaded);
  const r = {groups: document.querySelectorAll('#tree > details').length,
             parts: parts.length};
  const target = parts[0], original = target.material;
  select(target);
  r.selected = rowOf.get(target).classList.contains('sel')
    && target.material !== original;
  select(null);
  r.restored = target.material === original;
  raycaster.setFromCamera(new THREE.Vector2(0, 0), camera);
  r.picked = raycaster.intersectObjects(parts, false).length > 0;
  search.value = 'stiffener'; search.dispatchEvent(new Event('input'));
  r.hits = results.querySelectorAll('.row').length;
  document.body.dataset.selftest = JSON.stringify(r);
}, 50);
"""


def _chrome():
    import shutil
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac.exists():
        return str(mac)
    return shutil.which("google-chrome") or shutil.which("chromium")


@pytest.mark.browser
def test_viewer_loads_and_interacts_in_headless_chrome(tmp_path):
    """Needs Chrome and network access to unpkg.com (three.js)."""
    import html as html_lib
    import json
    import re
    import subprocess

    from ocx_render.gltf_writer import write_glb
    from ocx_render.render import render_model

    from tests.test_render_model import make_vessel

    chrome = _chrome()
    if chrome is None:
        pytest.skip("Chrome not installed")
    glb = write_glb(render_model(make_vessel()).meshes, tmp_path / "m.glb")
    page = write_html(glb).read_text(encoding="utf-8")
    end = page.rindex("</script>")   # inject into the viewer module's scope
    test_page = tmp_path / "selftest.html"
    test_page.write_text(page[:end] + _SELFTEST + page[end:], encoding="utf-8")
    dom = subprocess.run(
        [chrome, "--headless=new", "--enable-unsafe-swiftshader",
         "--virtual-time-budget=30000", "--dump-dom", test_page.as_uri()],
        capture_output=True, text=True, timeout=120).stdout
    m = re.search(r'data-selftest="([^"]*)"', dom)
    assert m, "viewer did not load: " + (re.search(
        r'<div id="status">([^<]*)', dom) or [None, "no status"])[1]
    r = json.loads(html_lib.unescape(m.group(1)))
    assert r == {"groups": 1, "parts": 2, "selected": True, "restored": True,
                 "picked": True, "hits": 1}
