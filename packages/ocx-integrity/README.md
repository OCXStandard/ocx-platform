# ocx-integrity

Canonical, salted per-aspect hashes and a Merkle manifest root for OCX models
(profile `ocx-hash/1`). The full specification is
`docs/superpowers/specs/2026-11-08-ocx-integrity-manifest-design.md`.

- Every part (plate, stiffener, bracket, pillar, edge reinforcement, panel,
  seam, compartment, plus one vessel-metadata part) gets a stable **part ID**:
  its GUID, or its XML id if it has no GUID.
- Each part is split into up to five **aspects**: `identity`, `material`,
  `scantlings`, `geometry`, `physical`. Each aspect is a canonical JSON record:
  SI decimal strings (fixed high-precision decimal context), resolved references
  (panel `SurfaceRef`s into `SurfaceCollection`s are inlined; `EdgeCurveRef`
  limits commit only the GUID), sorted sets, normalised closed contours (exact
  decimal Newell normals), serialised with RFC 8785 (JCS).
- `aspect_hash = SHA-256(salt ‖ JCS(payload))`, where
  `salt = HMAC-SHA256(K, "ocx-hash/1" ‖ 0 ‖ part_id ‖ 0 ‖ aspect)`. Without the
  key, hashes cannot be brute-forced against guessed scantlings.
- Part hashes are RFC 9162 Merkle roots of their aspect hashes. The manifest
  root is the Merkle root of all part hashes in UTF-8 byte order of the part IDs.
- The manifest contains only part IDs and salted hashes, so it is safe to share.
  The key `K` (≥ 32 bytes, hex) never leaves the yard.

## CLI

```bash
ocx-integrity keygen   -o yard.key                               # once; keep it secret
ocx-integrity manifest model.3docx --key yard.key -o manifest.json
ocx-integrity verify   model.3docx manifest.json --key yard.key  # exit 1 if anything changed
ocx-integrity prove    model.3docx manifest.json --key yard.key --part ID [--aspect A]... -o bundle.json
ocx-integrity check    bundle.json [--root HEX]                  # no key needed
ocx-integrity diff     old.json new.json [--format text|json]
```

The key can also be given via `OCX_INTEGRITY_KEY` (hex); `--key FILE` wins.
`keygen` creates the key file exclusively with owner-only permissions (0600 on
POSIX) and never overwrites an existing file. `prove` discloses all aspects
unless `--aspect` is given.
Exit codes:
- `0`: ok, match, or bundle valid.
- `1`: changes found, bundle invalid, or part drift on `prove`.
- `2`: cannot run (parse/build failure, bad key, existing key file on `keygen`,
  unsupported profile, malformed manifest or bundle (incl. duplicate JSON
  keys), tampered manifest (hashes that do not recompute), duplicate part IDs,
  unknown part/aspect). A bundle whose hashes do not check out is invalid
  (exit `1`).
- `3`: cannot write output.

Diffing manifests built with different keys reports every part as changed.

## Security notes

- Manifests are validated strictly on load: malformed JSON, duplicate keys or
  part/root hashes that do not recompute raise `IntegrityError`; a different
  profile raises `ProfileMismatchError`.
- A bundle's `tree_size` is not independently authenticated by the root. Pass
  `--root` from a trusted (signed) manifest, and if the part count matters,
  pin it from that authenticated manifest too.

## Python API

```python
from ocx_integrity import build_manifest, verify_model, prove, check_bundle, diff_manifests
```
