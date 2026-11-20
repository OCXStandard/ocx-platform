# Changelog — ocx-integrity

## 0.3.0 — 2026-11-20

- Requires `ocx-model-core>=0.6.1,<0.7` (reads `IrPlate.offset`).
- Plate `geometry` aspect includes the plate `offset`. Manifests built
  earlier for models whose plates carry `<Offset>` (including `0.0`) report
  a plate `geometry` change; plates without an offset hash as before.

## 0.2.1 — 2026-11-17

- Requires `ocx-model-core>=0.6,<0.7` (metadata only).

## 0.2.0 — 2026-11-16

- Profile `ocx-hash/1`: canonical per-aspect records for 9 part kinds, JCS
  serialisation, HMAC-derived salts, RFC 9162 Merkle part/model roots.
- Manifest build/save/load with consistency checks; verify and diff.
- Selective-disclosure proof bundles (`prove` / `check_bundle`).
- `ocx-integrity` CLI: `keygen`, `manifest`, `verify`, `prove`, `check`, `diff`.
- Identity records hash the effective `functionType` of panel children
  (own or inherited from the panel); bracket identity now includes it.
