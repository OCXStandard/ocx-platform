"""Aspect hashing: SHA-256(salt ‖ JCS(payload))."""

from __future__ import annotations

import hashlib
from typing import Any

import rfc8785

from ocx_integrity.profile import PROFILE


def payload(kind: str, part_id: str, aspect: str, record: dict[str, Any]) -> bytes:
    return rfc8785.dumps(
        {
            "profile": PROFILE,
            "kind": kind,
            "part_id": part_id,
            "aspect": aspect,
            "record": record,
        }
    )


def aspect_hash(salt: bytes, kind: str, part_id: str, aspect: str, record: dict[str, Any]) -> bytes:
    return hashlib.sha256(salt + payload(kind, part_id, aspect, record)).digest()
