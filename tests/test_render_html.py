"""Tests for the self-contained HTML viewer writer."""
import base64

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
