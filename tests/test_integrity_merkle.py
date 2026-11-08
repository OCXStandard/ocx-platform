"""RFC 9162 Merkle Tree Hash, inclusion paths and path verification."""

from __future__ import annotations

import hashlib

import pytest
from ocx_integrity.merkle import inclusion_path, mth, root_from_path


def L(d: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + d).digest()


def N(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _verifies(leaf, index, size, path, root) -> bool:
    try:
        return root_from_path(leaf, index, size, path) == root
    except ValueError:
        return False


def test_mth_empty_is_sha256_of_nothing():
    assert mth([]).hex() == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_mth_small_trees_follow_rfc9162_split():
    a, b, c, d, e = b"a", b"b", b"c", b"d", b"e"
    assert mth([a]) == L(a)
    assert mth([a, b]) == N(L(a), L(b))
    assert mth([a, b, c]) == N(N(L(a), L(b)), L(c))
    assert mth([a, b, c, d, e]) == N(N(N(L(a), L(b)), N(L(c), L(d))), L(e))


@pytest.mark.parametrize("n", [1, 2, 3, 7, 8, 1000])
def test_inclusion_paths_verify(n):
    leaves = [f"leaf{i}".encode() for i in range(n)]
    root = mth(leaves)
    indices = range(n) if n <= 8 else (0, 1, 511, 512, 999)
    for m in indices:
        assert root_from_path(leaves[m], m, n, inclusion_path(m, leaves)) == root


def test_path_lengths():
    leaves = [bytes([i]) for i in range(8)]
    assert len(inclusion_path(0, leaves)) == 3
    assert len(inclusion_path(6, leaves[:7])) == 2


def test_tampering_fails_verification():
    leaves = [f"leaf{i}".encode() for i in range(7)]
    root = mth(leaves)
    path = inclusion_path(3, leaves)
    assert _verifies(leaves[3], 3, 7, path, root)
    assert not _verifies(b"forged", 3, 7, path, root)
    assert not _verifies(leaves[3], 4, 7, path, root)
    # Index 3 has the same path shape for sizes 5..8, so use a size that changes it.
    assert not _verifies(leaves[3], 3, 4, path, root)
    assert not _verifies(leaves[3], 3, 7, [bytes(32)] + path[1:], root)


def test_malformed_inputs_raise():
    with pytest.raises(ValueError):
        root_from_path(b"a", 1, 1, [])  # index out of range
    with pytest.raises(ValueError):
        root_from_path(b"a", 0, 2, [])  # path too short
    with pytest.raises(ValueError):
        root_from_path(b"a", 0, 1, [bytes(32)])  # path too long
    with pytest.raises(ValueError):
        inclusion_path(5, [b"a"])
