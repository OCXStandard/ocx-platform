"""Yard-key handling and HMAC-derived per-(part, aspect) salts.

The key K never leaves this module's callers. Revealing one salt reveals
nothing about K or any other salt.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from collections.abc import Mapping
from pathlib import Path

from ocx_integrity.errors import InvalidKeyError
from ocx_integrity.profile import PROFILE

MIN_KEY_BYTES = 32
KEY_ENV = "OCX_INTEGRITY_KEY"


def derive_salt(key: bytes, part_id: str, aspect: str) -> bytes:
    message = b"\x00".join(
        (PROFILE.encode("utf-8"), part_id.encode("utf-8"), aspect.encode("utf-8"))
    )
    return hmac.new(key, message, hashlib.sha256).digest()


def parse_key(text: str) -> bytes:
    try:
        key = bytes.fromhex(text.strip())
    except ValueError as exc:
        raise InvalidKeyError("key is not valid hex") from exc
    if len(key) < MIN_KEY_BYTES:
        raise InvalidKeyError(f"key must be at least {MIN_KEY_BYTES} bytes (got {len(key)})")
    return key


def load_key(path: Path | None = None, env: Mapping[str, str] | None = None) -> bytes:
    """Read the hex key from ``path``, else from ``$OCX_INTEGRITY_KEY``."""
    if path is not None:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise InvalidKeyError(f"cannot read key file {path}: {exc}") from exc
        return parse_key(text)
    value = (os.environ if env is None else env).get(KEY_ENV)
    if not value:
        raise InvalidKeyError(f"no key given: pass --key FILE or set {KEY_ENV}")
    return parse_key(value)


def generate_key() -> str:
    """A fresh random key as hex text (64 hex chars = 32 bytes)."""
    return secrets.token_hex(MIN_KEY_BYTES)
