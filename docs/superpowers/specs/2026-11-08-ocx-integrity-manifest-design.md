# OCX integrity manifest (canonical salted aspect hashes + Merkle root) — design

**Date:** 2026-11-08
**Status:** approved (design), pending spec review

## Goal

Implement the *Foundation* of `docs/OCX_IP_Protection_Model_Based_Approval.md`:
a stable **part ID** plus a **canonical, salted per-aspect hash** for every
part, rolled up in a Merkle tree to a single **manifest root**. The yard keeps
the model; class receives the manifest (salted hashes only) and, on demand,
selective-disclosure bundles that prove individual part aspects belong to the
approved root.

Signing, trusted timestamping, MCP tools, RDF/RDFC-1.0 and external
(visual) geometry are **out of scope for v1**.

## Feasibility — why the IR is the right basis

- **Schema-neutral.** The builders already normalise OCX 2.8.6 / 3.0 / 3.1 /
  3.2 into one IR, so the hash is independent of the OCX schema version and
  of XML serialization noise (headers, element order, number formatting).
- **References resolvable.** Parts live in flat dicts keyed by id
  (`IrVessel.plates`, `.materials`, `.sections`, …), so material, section and
  hole-shape references can be inlined.
- **Units resolvable.** IR quantities carry raw OCX unit ids and
  `IrVessel.unit_registry` supplies SI factors.
- **Aspects map to IR fields** (see *Canonical records*).

Constraints accepted:

1. **Part ID stability** — the XML `id` is exporter-local; `guidref` is
   optional. Policy below.
2. **IR lossiness** — anything the builder drops is not committed. The
   profile is defined over the canonical record format; extending the IR
   requires a new profile version to commit new fields.
3. **Geometry equivalence** — v1 canonicalises closed-contour start point and
   orientation only; NURBS parametrisation is hashed as-is (stable across
   re-exports from the same tool, not across vendors).
4. **Interoperability** — the normative artefact is the canonical record
   format + hashing rules (profile `ocx-hash/1`); the Python IR extractors are
   its reference implementation.

## Decisions

| Topic | Decision |
|---|---|
| Serialization | JCS, RFC 8785 (`rfc8785` PyPI package, Trail of Bits) |
| Merkle tree | RFC 9162 Merkle Tree Hash (MTH), SHA-256 |
| Part ID | `guidref` if present, else XML `id` (recorded as `id_source: "xml_id"`) |
| Part kinds | plate, stiffener, bracket, pillar, edge_reinforcement, panel, seam, compartment, vessel (metadata) |
| Geometry | Parametric IR geometry only, canonical closed-contour start/orientation; no external-geometry leaf |
| Salts | Derived: `HMAC-SHA256(K, profile ‖ part_id ‖ aspect)`, K = yard master key |
| v1 features | manifest, verify, inclusion proof + disclosure bundle, diff, CLI |
| Packaging | New workspace member `ocx-integrity` → depends only on `ocx-model-core` |

## Package layout

```
packages/ocx-integrity/
  pyproject.toml           ← deps: ocx-model-core, rfc8785, typer, loguru
  src/ocx_integrity/
    __init__.py            ← public API: build_manifest, verify_model, prove, check_bundle, diff_manifests
    profile.py             ← PROFILE = "ocx-hash/1", ASPECTS order, precision table
    quantize.py            ← Quantity → SI decimal string via unit_registry
    canon_geom.py          ← canonical curve/surface dicts; closed-contour normalisation
    records/
      __init__.py          ← EXTRACTORS: {kind: extractor}; iter_parts(vessel)
      common.py            ← part_id(), ref → part id, material/section/hole records
      plate.py  stiffener.py  bracket.py  pillar.py  edge_reinforcement.py
      panel.py  seam.py  compartment.py  vessel.py
    salts.py               ← derive_salt(key, part_id, aspect), load_key()
    errors.py              ← IntegrityError, InvalidKeyError, DuplicatePartIdError,
                             ProfileMismatchError, UnknownPartError, PartDriftError
    hashing.py             ← aspect_hash()
    merkle.py              ← mth(), inclusion_path(), root_from_path()
    manifest.py            ← Manifest dataclass, build_manifest(), load/save JSON
    verify.py              ← verify_model(vessel, manifest, key) → ChangeReport
    diff.py                ← diff_manifests(manifest_a, manifest_b) → ChangeReport
    proof.py               ← prove(...) → DisclosureBundle; check_bundle(bundle, root=None)
    cli.py                 ← `ocx-integrity` entrypoint
```

The CLI uses `typer` + `loguru`, matching `ocx_render/cli.py`.

## Canonical records

Each extractor returns `{aspect: record_dict}` for one part. Aspects (fixed
order): `identity`, `material`, `scantlings`, `geometry`, `physical`. An
aspect with no content for a part is **absent** (no leaf). `kind` and
`part_id` are bound by the hashed payload (see *Hashing*), so the `identity`
record itself carries `id_source` and the remaining identity fields.
Curve `curve_length` values are excluded from `geometry` and committed under
`physical` (they are derived values).

| Kind | identity | material | scantlings | geometry | physical |
|---|---|---|---|---|---|
| plate | kind, part_id, id_source, name, function_type, parent part_id | resolved material | thickness, renewal_thickness, voluntary_thickness_addition | outer_contour, cut_by_contours, cut_by_holes (resolved hole shape + transformation), point_on_surface | mass_properties, net_area, curve lengths |
| stiffener | as plate | resolved material | resolved section, web/flange renewal + voluntary additions, end_cut_end1/2 | trace, trace_refs (part ids), inclinations, orientation_rule, penetrations | mass_properties, trace length |
| bracket | as plate | resolved material | thickness, renewal, voluntary, arm_length_u/v, unose/vnose, free_edge_radius, edge reinforcement flags, flange_width/radius, feature_cope | origin, u/vdirection, outer_contour, plane, offset | mass_properties |
| pillar | as plate | resolved material | resolved section, renewal + voluntary additions | trace, inclinations, penetrations | mass_properties |
| edge_reinforcement | as plate | resolved material | resolved section, renewal + voluntary additions | trace_refs, orientation_rule | mass_properties |
| panel | kind, part_id, id_source, name, function_type, tightness, child part ids (sorted per kind) | — | — | unbounded_geometry, limited_by (part ids + type + bounds), outer_contours, cut_by_* , point_on_surface | mass_properties |
| seam | kind, part_id, id_source, name | — | — | trace_line, trace_refs | trace_line length |
| compartment | kind, part_id, id_source, name, compartment_purpose, filling_height, air_pipe_height, relief_valve_pressure | — | — | face_refs (part ids, sorted), face_boundary_curves (canonical, sorted) | volume, cog, curve lengths |
| vessel | kind, part_id, ship_designation, principal_particulars, builder_info, statutory_data, tonnage_data | — | — | — | — |

The vessel part ID is `vessel:<IrVessel.id>` (`id_source: "vessel"`).
`IrHeader` (timestamps, author, originating system) is deliberately **not**
hashed. Physical spaces, cargoes, design views, surfaces/ref-planes as
standalone items and connection configurations get no leaves in v1; surfaces
and ref planes are committed indirectly where a panel's `unbounded_geometry`
resolves them (inlined canonical surface / ref-plane record).

Resolved catalogue records (inlined, not separate leaves):
- **material**: material_type, grade, density, yield_stress, ultimate_stress,
  youngs_modulus, poisson_ratio, thermal_expansion, aluminium strengths,
  alloy_designation, plus the material's own part ID.
- **section**: section type + all dimension quantities from `IrSection`,
  plus its part ID.
- **hole**: parametric variant + dimensions, or canonical contour, plus its
  part ID.

### Normalisation rules

1. **Quantities** → SI via `unit_registry[unit].to_si_factor`, emitted as
   decimal **strings** with fixed decimals per dimension (never JSON floats):

   | Dimension | SI unit (`IrUnit.si_symbol`) | Decimals |
   |---|---|---|
   | length, coordinates | m | 6 (1 µm) |
   | area | m² | 6 |
   | volume | m³ | 6 |
   | second moment of area | m⁴ | 9 |
   | stress / modulus | Pa | 0 |
   | mass (incl. `UkN`, mapped to kg by the registry) | kg | 3 |
   | density | kg/m³ | 3 |
   | velocity | m/s | 6 |
   | moment | N·m | 3 |
   | dimensionless / angle / any other symbol (ratio, direction components, weights, knots) | — | 6 |

   The dimension is taken from the unit's `IrUnit.si_symbol`; bare floats
   (e.g. direction components, NURBS weights/knots) use 6 decimals.

   Rounding: `decimal.ROUND_HALF_EVEN`; `-0` normalised to `0`.
   Unknown unit → value kept raw with `"unit": <id>` and a manifest warning.
2. **References** → part IDs (guid-or-id policy), never XML ids.
   Unresolvable → `{"unresolved": <raw local_ref/guid>}` + manifest warning.
3. **Unordered collections** (cut_by_holes, cut_by_contours, limited_by,
   penetrations, child ids, trace_refs where unordered) sorted by their JCS
   bytes. **Ordered** collections (polyline vertices, composite segments,
   knots, control points) keep order.
4. **Closed contours** (closed polyline; composite whose last end == first
   start within 1 µm):
   - rotate so the segment/vertex starting at the lexicographically smallest
     quantised point (x, y, z) comes first; ties between equal start points
     are broken by the lexicographically smallest full rotated sequence
     (per segment: start point, then the segment's JCS bytes);
   - compute the Newell normal in exact decimal arithmetic on the quantised
     coordinates; if its dominant component (largest absolute
     value; ties resolved x > y > z) is negative, reverse orientation (reverse
     vertex order / reverse segments and each segment's direction), then
     re-apply the start-point rotation.
   Open curves and standalone NURBS curves are kept as-is; a NURBS segment
   inside a reversed closed composite is reversed with it (control points
   and weights reversed, knots mirrored).
5. `None`, empty strings, empty lists/dicts and `False` are **omitted** as
   object members; list elements are positional and are kept.
6. Every record carries `"kind"`; every nested IR object dict (curves,
   surfaces, sections, materials, mass properties, …) carries `"type"`
   (lowercase IR class name without `Ir` prefix). Nested XML `id`/`guidref`
   fields are dropped (exporter-local); catalogue objects carry their
   `part_id` instead.
7. Points with an unknown unit are emitted as `[x, y, z, unit_id]` (raw
   values, 6 decimals) with a manifest warning.

## Hashing and Merkle construction

```
salt        = HMAC-SHA256(K, utf8("ocx-hash/1") ‖ 0x00 ‖ utf8(part_id) ‖ 0x00 ‖ utf8(aspect))
payload     = JCS({"profile": "ocx-hash/1", "kind": kind, "part_id": part_id,
                   "aspect": aspect, "record": record})
aspect_hash = SHA256(salt ‖ payload)
part_hash   = MTH([aspect_hash for aspect in ASPECTS if present])     # RFC 9162
root        = MTH([part_hash for part_id in sorted(part_ids)])        # UTF-8 byte order
```

RFC 9162 MTH: leaf = `SHA256(0x00 ‖ data)`, node = `SHA256(0x01 ‖ left ‖ right)`,
split at the largest power of two < n. Empty tree = `SHA256("")`.

- K is ≥ 32 bytes, read from `--key FILE` or `OCX_INTEGRITY_KEY` (hex).
  K is never written to any output.
- Revealing one salt reveals nothing about K or other salts.
- Unchanged aspects keep the same hash across revisions (same K) → change
  classification works.

## Manifest format (`manifest.json`)

```json
{
  "profile": "ocx-hash/1",
  "created": "2026-11-08T12:00:00Z",
  "source": {"file": "model.3docx", "sha256": "…", "schema_version": "3.1.0"},
  "root": "<hex>",
  "part_count": 1234,
  "warnings": ["unresolved material ref 'M9' on plate P12", "…"],
  "parts": {
    "<part_id>": {
      "kind": "plate",
      "id_source": "guid",
      "part_hash": "<hex>",
      "aspects": {"identity": "<hex>", "material": "<hex>", "…": "…"}
    }
  }
}
```

The manifest contains only salted hashes and part IDs — safe to share with
class. `created` and `source` are informational and not part of the root.

## Disclosure bundle (`bundle.json`)

```json
{
  "profile": "ocx-hash/1",
  "root": "<hex>",
  "tree_size": 1234,
  "leaf_index": 17,
  "part_id": "<id>", "kind": "plate",
  "disclosed": {"scantlings": {"record": {…}, "salt": "<hex>"}},
  "aspect_hashes": {"identity": "<hex>", "material": "<hex>", "scantlings": "<hex>", "…": "…"},
  "audit_path": ["<hex>", "…"]
}
```

`check_bundle` (no key needed): recompute each disclosed aspect hash from
record + salt, confirm it equals `aspect_hashes[aspect]`, recompute
`part_hash` from `aspect_hashes`, then recompute the root from `leaf_index`,
`tree_size` and `audit_path`; compare to `root` (and to `--root` if given).

## Verify and diff

`ChangeReport`: `added`, `removed`, `changed: {part_id: [aspects]}`,
`unchanged_count`, `root_a`, `root_b`.

- `verify_model(vessel, manifest, key)` rebuilds a manifest and diffs it against
  the stored one.
- `diff_manifests(a, b)` compares two manifests; requires equal `profile` (refuses
  otherwise). Using different K yields "everything changed" — documented,
  not detected.

## CLI

```
ocx-integrity keygen   -o yard.key
ocx-integrity manifest model.3docx --key yard.key -o manifest.json
ocx-integrity verify   model.3docx manifest.json --key yard.key
ocx-integrity prove    model.3docx manifest.json --key yard.key --part ID [--aspect A]... -o bundle.json
ocx-integrity check    bundle.json [--root HEX]
ocx-integrity diff     old.json new.json [--format text|json]
```

Exit codes: `0` ok / match / bundle valid · `1` mismatch, changes found, or
bundle invalid · `2` cannot run (parse/build failure, bad key, unknown
profile, duplicate part IDs, unknown `--part`) · `3` cannot write output.

`prove` first verifies that the rebuilt part hash equals the manifest entry
(exit 1 otherwise) so a bundle is never issued for a drifted model.
Without `--aspect`, all aspects are disclosed.

## Error handling

- Parse/build failures surface as core exceptions (`exeptions.py`) → exit 2.
- Missing key or key < 32 bytes → exit 2 with a clear message.
- **Duplicate part IDs** (e.g. a GUID reused by two parts) → hard error,
  exit 2, listing the duplicates.
- Unresolved refs and unknown units → manifest `warnings`, not fatal.
- Loading a manifest/bundle with `profile != "ocx-hash/1"` → refused, exit 2.
- Loading a manifest whose `root`/`part_hash` values do not recompute from
  its own entries → refused (`IntegrityError`), exit 2.
- Logging via `loguru` only.

## Testing (shared `tests/`)

- `test_integrity_golden.py` — hand-built small `IrVessel` (plate, stiffener,
  panel, material, section) + fixed key; expected aspect hashes, part hashes
  and root pinned in `tests/data/integrity/golden_v1.json`. Guards the
  profile against accidental change.
- `test_integrity_canon.py` — invariance: reversed / rotated closed contour,
  mm vs m units, reordered holes and limited_by, sub-precision float noise →
  identical hashes. Thickness change → only `scantlings` differs; weight
  change → only `physical` differs.
- `test_integrity_merkle.py` — RFC 9162 MTH known values; inclusion paths for
  n = 1, 2, 3, 7, 8, 1000; path verification.
- `test_integrity_proof.py` — bundle verifies without key; tampered record,
  salt, aspect hash, path or root each fail.
- `test_integrity_diff.py` — added / removed / changed classification;
  profile mismatch refused.
- `test_integrity_cli.py` — CLI on a synthetic vessel (`_load_vessel`
  monkeypatched, as in `test_render_cli.py`): `manifest` → `verify` exit 0;
  edited vessel → exit 1; `prove` → `check` exit 0; bad key → exit 2.
- `test_integrity_model.py` — real model `models/TR02/TR02_TC01_ai3dx.3docx`
  (tracked, 15 kB): manifest → verify clean; prove → check valid. (No
  content-identical 3.1.0/3.2.0 model pair exists in the repo, so the
  cross-version equal-root check is deferred until one is added.)

## Out of scope (later phases)

- Signing the root (Ed25519 / JWS / VC Data Integrity), yard + class co-sign.
- RFC 3161 timestamping.
- MCP tools in `ocx-mcp`.
- External geometry (`ExternalGeometryRef`) visual leaf.
- Cross-vendor geometry equivalence (sampled/tessellated fingerprint).
- RDF / RDFC-1.0 profile.
