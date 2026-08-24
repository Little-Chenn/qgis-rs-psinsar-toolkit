# Remote Sensing and PS-InSAR Processing & Mapping Toolkit

**English** | [简体中文](README_zh-CN.md)

This is the independent local open-source preparation repository for the
bilingual QGIS plugin `rs_psinsar_toolkit` version `0.3.0-rc1`.

- Author: **Yang Chenxi (杨晨曦)**
- Affiliation: **Xiamen University Joint Remote Sensing Receiving Station
  (厦门大学联合遥感接收站)**
- Public contact: **cyang5533@gmail.com**
- Planned public repository:
  **<https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit>**
- Supported validation runtime: **QGIS 3.44.11-Solothurn**
- Status: **experimental pre-release candidate; not yet published**

The affiliation identifies the author's stated institutional affiliation and
does not by itself imply institutional ownership, sponsorship, certification,
or endorsement.

The `0.3.0-rc1` source is promoted from the locally qualified
`0.3.0-dev.8-bilingual-rc3` candidate. That candidate passed fresh native ZIP
installation, 39 automated tests, English six-module GUI smoke testing,
Chinese/English six-module lightweight regression, numeric comparison, three
thematic-map regression, and the author's manual installation and visual
acceptance. The version and licensing promotion is being requalified locally
before any external publication.

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

No remote Git repository is configured. No commit, push, GitHub Release, QGIS
Plugin Repository submission, or public upload has been performed. The GitHub
owner and final metadata URLs are confirmed for local packaging, but external
connection and publication still require separate explicit authorization.

For usage documentation, see the
[plugin README](rs_psinsar_toolkit/README.md),
[installation guide](rs_psinsar_toolkit/INSTALL.md), and
[user guide](rs_psinsar_toolkit/USER_GUIDE.md).
