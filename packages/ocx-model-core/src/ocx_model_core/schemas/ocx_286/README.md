# OCX 2.8.6 vendored schema

- `OCX_Schema.xsd` — from https://github.com/OCXStandard/OCX_Schema, tag `v2.8.6`
  (namespace `http://data.dnvgl.com/Schemas/ocxXMLSchema`), with its single
  XSD 1.1 `<xs:assert>` element removed so the schema compiles under lxml
  (libxml2 supports XSD 1.0 only). The assert only enforced that an
  `EntityRefBase` carries a `localRef` and/or a `GUIDRef`; validation is
  otherwise unchanged. Do not use the `v2.8.6_fix` tag — it pins
  `schemaVersion="2.8.6_fix"`, which real 2.8.6 models do not declare.
- `unitsmlSchema_lite-0.9.18.xsd` — same file as vendored for 3.x
  (copied from `../ocx_310/`). Note: the copy shipped inside the `ocx`
  PyPI package's `ocx_286/` folder is corrupt (it is actually the OCX
  3.0.1 schema) and must not be used.
