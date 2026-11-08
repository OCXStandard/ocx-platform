"""CLI tests for `ocx-integrity` (synthetic vessel via a patched _load_vessel)."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import ocx_integrity.cli as cli_mod
import pytest
from ocx_integrity.cli import app
from ocx_integrity.salts import KEY_ENV, parse_key
from ocx_model_core.model.ir import Quantity
from typer.testing import CliRunner

from tests.integrity_fixtures import KEY, make_vessel

runner = CliRunner()


def _invoke(*args):
    return runner.invoke(app, [str(a) for a in args])


def _edited_vessel(model):
    v = make_vessel()
    v.plates["PL1"].thickness = Quantity(14.0, "Umm")
    return v


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.setattr(cli_mod, "_load_vessel", lambda model: make_vessel())
    model = tmp_path / "m.3docx"
    model.write_text("<x/>", encoding="utf-8")
    key = tmp_path / "yard.key"
    key.write_text(KEY.hex() + "\n", encoding="utf-8")
    return SimpleNamespace(tmp=tmp_path, model=model, key=key, manifest=tmp_path / "manifest.json")


def _make_manifest(env, output=None):
    output = output or env.manifest
    result = _invoke("manifest", env.model, "--key", env.key, "-o", output)
    assert result.exit_code == 0, result.output
    return output


def test_keygen_writes_key_and_refuses_overwrite(tmp_path):
    out = tmp_path / "yard.key"
    result = _invoke("keygen", "-o", out)
    assert result.exit_code == 0, result.output
    assert len(parse_key(out.read_text(encoding="utf-8"))) == 32
    assert out.read_text(encoding="utf-8").strip() not in result.stdout
    assert _invoke("keygen", "-o", out).exit_code == 2


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_keygen_creates_owner_only_file(tmp_path):
    out = tmp_path / "yard.key"
    assert _invoke("keygen", "-o", out).exit_code == 0
    assert out.stat().st_mode & 0o077 == 0


def test_manifest_then_verify_clean(env):
    _make_manifest(env)
    text = env.manifest.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["part_count"] == 6
    assert data["source"]["file"] == "m.3docx"
    assert data["created"].endswith("Z")
    assert KEY.hex() not in text
    result = _invoke("verify", env.model, env.manifest, "--key", env.key)
    assert result.exit_code == 0, result.output
    assert "match: 6 parts unchanged" in result.stdout


def test_manifest_default_output_and_env_key(env, monkeypatch):
    monkeypatch.setenv(KEY_ENV, KEY.hex())
    result = _invoke("manifest", env.model)
    assert result.exit_code == 0, result.output
    assert (env.tmp / "m.manifest.json").exists()


def test_verify_edited_model_exits_1(env, monkeypatch):
    _make_manifest(env)
    monkeypatch.setattr(cli_mod, "_load_vessel", _edited_vessel)
    result = _invoke("verify", env.model, env.manifest, "--key", env.key)
    assert result.exit_code == 1
    assert "  G-PL-1: scantlings" in result.stdout


def test_prove_then_check(env):
    _make_manifest(env)
    root = json.loads(env.manifest.read_text(encoding="utf-8"))["root"]
    bundle = env.tmp / "bundle.json"
    result = _invoke(
        "prove",
        env.model,
        env.manifest,
        "--key",
        env.key,
        "--part",
        "G-PL-1",
        "--aspect",
        "scantlings",
        "-o",
        bundle,
    )
    assert result.exit_code == 0, result.output
    assert list(json.loads(bundle.read_text(encoding="utf-8"))["disclosed"]) == ["scantlings"]

    result = _invoke("check", bundle, "--root", root)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("VALID")
    assert _invoke("check", bundle, "--root", "00" * 32).exit_code == 1

    data = json.loads(bundle.read_text(encoding="utf-8"))
    data["disclosed"]["scantlings"]["salt"] = "00" * 32
    bundle.write_text(json.dumps(data), encoding="utf-8")
    result = _invoke("check", bundle)
    assert result.exit_code == 1
    assert result.stdout.startswith("INVALID")


def test_prove_unknown_part_exits_2_and_drift_exits_1(env, monkeypatch):
    _make_manifest(env)
    out = env.tmp / "b.json"
    args = ("prove", env.model, env.manifest, "--key", env.key, "-o", out)
    assert _invoke(*args, "--part", "NOPE").exit_code == 2
    assert _invoke(*args, "--part", "G-PL-1", "--aspect", "bogus").exit_code == 2
    monkeypatch.setattr(cli_mod, "_load_vessel", _edited_vessel)
    assert _invoke(*args, "--part", "G-PL-1").exit_code == 1
    assert not out.exists()


def test_diff_text_and_json(env, monkeypatch):
    old = _make_manifest(env)
    monkeypatch.setattr(cli_mod, "_load_vessel", _edited_vessel)
    new = _make_manifest(env, env.tmp / "new.json")
    result = _invoke("diff", old, new)
    assert result.exit_code == 1
    assert "  G-PL-1: scantlings" in result.stdout
    result = _invoke("diff", old, new, "--format", "json")
    assert result.exit_code == 1
    assert json.loads(result.stdout)["changed"] == {"G-PL-1": ["scantlings"]}
    assert _invoke("diff", old, old).exit_code == 0
    assert _invoke("diff", old, new, "--format", "xml").exit_code == 2


@pytest.mark.parametrize("key_text", ["abcd", "not hex at all"])
def test_bad_key_exits_2(env, key_text):
    env.key.write_text(key_text, encoding="utf-8")
    assert _invoke("manifest", env.model, "--key", env.key, "-o", env.manifest).exit_code == 2
    assert not env.manifest.exists()


def test_missing_key_exits_2(env):
    assert _invoke("manifest", env.model, "-o", env.manifest).exit_code == 2


def test_duplicate_part_ids_exit_2(env, monkeypatch):
    def duplicated(model):
        v = make_vessel()
        v.stiffeners["ST1"].guidref = "G-PL-1"
        return v

    monkeypatch.setattr(cli_mod, "_load_vessel", duplicated)
    assert _invoke("manifest", env.model, "--key", env.key, "-o", env.manifest).exit_code == 2


def test_tampered_or_foreign_manifest_exits_2(env):
    _make_manifest(env)
    data = json.loads(env.manifest.read_text(encoding="utf-8"))
    data["root"] = "00" * 32
    env.manifest.write_text(json.dumps(data), encoding="utf-8")
    assert _invoke("verify", env.model, env.manifest, "--key", env.key).exit_code == 2
    data["profile"] = "ocx-hash/2"
    env.manifest.write_text(json.dumps(data), encoding="utf-8")
    assert _invoke("diff", env.manifest, env.manifest).exit_code == 2
    _make_manifest(env)
    text = env.manifest.read_text(encoding="utf-8").rstrip()
    root = json.loads(text)["root"]
    env.manifest.write_text(text[:-1] + f', "root": "{root}"}}', encoding="utf-8")
    assert _invoke("diff", env.manifest, env.manifest).exit_code == 2
    env.manifest.write_text("not json", encoding="utf-8")
    assert _invoke("verify", env.model, env.manifest, "--key", env.key).exit_code == 2


def test_unparseable_model_exits_2(tmp_path, monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    bad = tmp_path / "bad.3docx"
    bad.write_text("this is not xml", encoding="utf-8")
    key = tmp_path / "yard.key"
    key.write_text(KEY.hex(), encoding="utf-8")
    assert _invoke("manifest", bad, "--key", key, "-o", tmp_path / "m.json").exit_code == 2


def test_write_failure_exits_3(env):
    out = env.tmp / "missing-dir" / "manifest.json"
    assert _invoke("manifest", env.model, "--key", env.key, "-o", out).exit_code == 3
