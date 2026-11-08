"""RFC 9162 §2.1 Merkle Tree Hash (SHA-256), inclusion paths and verification."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    """Largest power of two strictly less than n (n > 1)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def mth(leaves: Sequence[bytes]) -> bytes:
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return leaf_hash(leaves[0])
    k = _split(n)
    return node_hash(mth(leaves[:k]), mth(leaves[k:]))


def inclusion_path(index: int, leaves: Sequence[bytes]) -> list[bytes]:
    """RFC 9162 PATH(m, D[n]) — sibling hashes from leaf to root."""
    n = len(leaves)
    if not 0 <= index < n:
        raise ValueError(f"leaf index {index} out of range for tree size {n}")
    if n == 1:
        return []
    k = _split(n)
    if index < k:
        return inclusion_path(index, leaves[:k]) + [mth(leaves[k:])]
    return inclusion_path(index - k, leaves[k:]) + [mth(leaves[:k])]


def root_from_path(leaf: bytes, index: int, size: int, path: Sequence[bytes]) -> bytes:
    """RFC 9162 §2.1.3.2: recompute the root from leaf data + audit path.

    Raises ValueError if the index is out of range or the path length is wrong.
    """
    if not 0 <= index < size:
        raise ValueError(f"leaf index {index} out of range for tree size {size}")
    fn, sn = index, size - 1
    r = leaf_hash(leaf)
    for p in path:
        if sn == 0:
            raise ValueError("audit path too long")
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    if sn != 0:
        raise ValueError("audit path too short")
    return r
