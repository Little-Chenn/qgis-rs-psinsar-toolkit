# Contributing

This project is still in local publication preparation. Contributions should
preserve the following review gates.

## Required behavior

- Treat inputs as read-only and write every run to a new isolated directory.
- Do not translate JSON keys, machine statuses, field names, formulas, internal
  compatibility filenames, or algorithm identifiers.
- Preserve the reviewed scientific boundaries documented in the root README.
- Add user-visible Chinese text as a stable source string and provide a reviewed
  English Qt translation with placeholder parity.
- Keep scientific rasters separate from display-only products.
- Add or update automated tests for behavior changes.

## Local validation

Run the complete `tests/test_*.py` suite inside the supported QGIS Python/Qt
runtime. For release candidates, also perform fresh ZIP installation, Chinese
and English GUI smoke checks, one lightweight run per module, and cross-language
numeric comparison.

Do not add raw satellite imagery, personal datasets, local QGIS profiles,
validation outputs, credentials, absolute personal paths, or unclear-license
assets to a contribution.

Contributions to software and runtime resources must be compatible with
`GPL-2.0-or-later`. Contributions to English or Chinese documentation must be
compatible with `CC BY 4.0` and must identify reused third-party material.
