# 0.3.0-rc1 Bilingual Pre-release Candidate

**English** | [简体中文](RELEASE_NOTES_zh-CN.md)

## Candidate scope

`0.3.0-rc1` promotes the locally qualified
`0.3.0-dev.8-bilingual-rc3` candidate into a public-version naming scheme in an
independent open-source preparation repository. It does not overwrite the
`0.2.3` release baseline, the dev.6 Chinese source candidate, the qualified
dev.8 source, or the RC3 ZIP.

The promotion adds the confirmed licenses, copyright, author affiliation,
public contact, and release-candidate version. It does not intentionally change
scientific algorithms, numeric values, machine-facing fields, formulas, or
accepted thematic-map templates.

## Internationalization and layout

- Qt `.ts/.qm` catalogs follow the QGIS interface language.
- The Task Center, six module interfaces, validation, progress, logs, errors,
  and human-readable reports are available in Chinese and English.
- English QPT derivatives are provided for SAR intensity, vertical
  displacement-rate, and cumulative-displacement mapping.
- The accepted English maps use Times New Roman for visible English text.
- Modules 1 and 2 are resizable and use compact scrollable layouts for smaller
  displays.
- Output directory names, filenames, data fields, JSON keys, formulas,
  selection-mode values, and machine-readable statuses remain language-neutral
  and unchanged.

## Scientific wording

- The GCP workflow is external-GCP image-to-map geometric correction, not
  Range-Doppler terrain correction.
- Without complete Sigma0/Gamma0 calibration evidence, SAR products are
  described as `SAR intensity (dB)`, not calibrated backscatter.
- Vertical displacement rate is in `mm/year`, with positive values upward and
  negative values downward.
- Cumulative displacement is in `mm`; the fixed calculation order is
  pointwise `D_target - D_initial`, followed by the median of valid differences
  in each 50 m grid. Stored values are not rescaled.
- Multi-point time-series output is descriptive evidence for manual review and
  does not automatically identify anomalies, classify trends, or infer causes.
- Float32 scientific rasters remain separate from 8-bit display products.

## Licensing and attribution

- Software, tests, QPT templates, Qt catalogs, SVG assets, and runtime
  resources: `GPL-2.0-or-later`.
- English and Simplified Chinese documentation: `CC BY 4.0`.
- Copyright (C) 2026 Yang Chenxi (杨晨曦).
- Author affiliation: Xiamen University Joint Remote Sensing Receiving Station
  (厦门大学联合遥感接收站).

The affiliation is an author-identification statement and does not by itself
imply institutional ownership or endorsement.

## Verification status

The source baseline and internal RC3 passed QGIS 3.44.11 fresh native ZIP
installation, 39 automated tests, English six-module GUI smoke testing,
Chinese/English six-module lightweight regression, numeric comparison, three
thematic-map regression, and author manual acceptance. The formal local RC1 ZIP
subsequently passed fresh Chinese and English native installation, seven-window
GUI smoke checks, 39/39 installed-copy tests, and three-map numeric/template
regression.

## Publication status

A formal `0.3.0-rc1` ZIP has been built and validated locally. No GitHub upload,
remote push, public Release, or QGIS Plugin Repository submission has been
performed. External publication requires separate explicit authorization.
