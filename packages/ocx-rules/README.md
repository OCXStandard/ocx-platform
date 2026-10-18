# ocx-rules

Configurable best-practice rule engine for OCX `.3docx` models.

Rules are defined declaratively in TOML files and bind either a named check
primitive from the built-in library or a custom Python callable. Rule packs are
discovered through the `ocx_rules.packs` entry-point group. See
`docs/superpowers/specs/2026-10-18-ocx-rule-validation-design.md` in the repo
root for the full design.
