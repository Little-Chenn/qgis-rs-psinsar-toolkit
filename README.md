# Remote Sensing and PS-InSAR Processing & Mapping Toolkit

**English** | [简体中文](README_zh-CN.md)

This is the public source repository for the
bilingual QGIS plugin `rs_psinsar_toolkit` version `0.3.0-rc1`.

- Author: **Yang Chenxi (杨晨曦)**
- Affiliation: **Xiamen University Joint Remote Sensing Receiving Station
  (厦门大学联合遥感接收站)**
- Public contact: **cyang5533@gmail.com**
- Source repository:
  **<https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit>**
- Supported validation runtime: **QGIS 3.44.11-Solothurn**
- Status: **experimental pre-release candidate (`0.3.0-rc1`)**

This project is developed and maintained by the author. The affiliation above
identifies the institution with which the author is affiliated.

The `0.3.0-rc1` source is promoted from the locally qualified
`0.3.0-dev.8-bilingual-rc3` candidate. That candidate passed fresh native ZIP
installation, 39 automated tests, English six-module GUI smoke testing,
Chinese/English six-module lightweight regression, numeric comparison, three
thematic-map regression, and the author's manual installation and visual
acceptance. For validation details of the published `0.3.0-rc1` package, see the
[release notes](https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit/releases/tag/v0.3.0-rc1).

## Repository layout

- [`rs_psinsar_toolkit/`](rs_psinsar_toolkit/) — installable plugin source,
  bilingual documentation, Qt catalogs, assets, and QPT templates;
- [`tests/`](tests/) — internationalization, scientific-contract, geometry,
  SAR, and time-series regression tests;
- [`tools/`](tools/) — guarded local packaging and repository-audit tools;
- [`OPEN_SOURCE_AUDIT.md`](OPEN_SOURCE_AUDIT.md) — current privacy, dependency,
  security, metadata, and asset review;
- [`LICENSING.md`](LICENSING.md) — software/documentation license scope;
- [`AUTHORS.md`](AUTHORS.md) — author, affiliation, and public contact;
- [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) — local-to-public release gates.

## Scientific boundaries

- SAR output is described as intensity in dB unless complete calibration
  evidence supports a stronger Sigma0/Gamma0 claim.
- External-GCP image-to-map correction is not Range-Doppler terrain correction.
- Vertical displacement rate is in `mm/year`.
- Cumulative displacement retains `D_target - D_initial`, followed by the
  median of valid differences within each 50 m grid; displacement is in `mm`,
  with positive values upward and negative values downward.
- Multi-point time-series output supports descriptive manual review and does
  not automatically identify anomalies, classify trends, or infer causes.
- Inputs are read-only and each task creates an isolated, non-overwriting output
  directory.

## Licensing

- Software source, tests, QPT templates, Qt catalogs, SVG assets, and runtime
  resources: [`GPL-2.0-or-later`](LICENSE).
- English and Simplified Chinese documentation:
  [`CC BY 4.0`](LICENSE-DOCUMENTATION.md).
- Third-party components remain under their own terms; see
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Copyright (C) 2026 Yang Chenxi (杨晨曦).

## Publication status

The source code is publicly available in this repository. The `0.3.0-rc1`
pre-release, including the installable plugin ZIP and release notes, is available
on [GitHub Releases](https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit/releases/tag/v0.3.0-rc1).

This is an experimental release candidate intended for testing and feedback.
Users should validate outputs against their own data and project requirements
before relying on them in research or operational workflows.

For usage documentation, see the
[plugin README](rs_psinsar_toolkit/README.md),
[installation guide](rs_psinsar_toolkit/INSTALL.md), and
[user guide](rs_psinsar_toolkit/USER_GUIDE.md).
