# 0.3.0-rc1 Bilingual Pre-release: Installation and Short Acceptance

**English** | [简体中文](INSTALL_zh-CN.md)

## Installation

Download `rs_psinsar_toolkit-0.3.0-rc1.zip` from
[GitHub Releases](https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit/releases/tag/v0.3.0-rc1),
then install it in QGIS:

1. Open **Plugins → Manage and Install Plugins** in QGIS.
2. Select **Install from ZIP**.
3. Select the validated `rs_psinsar_toolkit-0.3.0-rc1.zip`.
4. If QGIS reports an existing plugin with the same ID, confirm the candidate upgrade
   only in the intended test profile.
5. Open **Remote Sensing and PS-InSAR Processing & Mapping Toolkit** from the plugin
   menu or toolbar.

For initial testing, use a separate QGIS profile to keep your existing plugin
installation and settings available.

## Language acceptance

The plugin follows the QGIS interface language. Test in separate QGIS launches:

1. Set the QGIS locale to Simplified Chinese (`zh_CN`), restart QGIS, and inspect the
   Task Center and all six modules.
2. Set the QGIS locale to English, restart QGIS, and repeat the inspection.
3. Confirm that the matching Chinese or English bundled QPT is used for modules 3–5.
4. Confirm that machine-facing output directories, filenames, JSON keys, data fields,
   formulas, and status values remain unchanged.

## Interface short acceptance

The Task Center must show two columns and three rows:

1. GCP-based Geometric Correction and Accuracy Assessment;
2. SAR Image Mosaicking, Mask Clipping and Display Enhancement;
3. SAR Intensity Mapping in dB;
4. PS-InSAR Vertical Displacement Rate Mapping;
5. Batch Mapping of PS-InSAR Cumulative Displacement;
6. PS-InSAR Multi-point Displacement Time-series Review.

Check that window titles do not contain candidate or engine versions, descriptions stay
inside their cards, buttons and labels are not clipped, and longer English text wraps
without covering controls. The SAR processing page must remain scrollable.

## Functional short acceptance

- **GCP:** open both the correction and workflow-validation tabs; inspect scope,
  control-point fields, and RMSE wording.
- **SAR processing:** scan a single-scene ORG input and check display settings and
  scientific acknowledgement dependencies.
- **SAR intensity map:** read a dB image and inspect the right-side text preview and
  export settings.
- **Displacement-rate map:** inspect polygon-grid input, value field, basemap, and map
  information.
- **Cumulative displacement:** scan epochs and inspect D0/Dt semantics, date selection,
  and reference-epoch behavior.
- **Time-series review:** inspect both a ranked point list and a complete candidate
  table; confirm controlled-sampling controls are enabled only for the latter.

Every execution must create a new timestamped directory under the selected output root
and leave the input unchanged. The target validation environment is QGIS `3.44.11`.

## Validation status

The local RC1 ZIP passed native installation in fresh Chinese and English QGIS 3.44.11
profiles, seven-window GUI smoke checks, 39/39 installed-copy tests, and the three-map
numeric/template regression. The earlier bilingual RC3 also passed the user's manual
six-module and three-map acceptance. These checks cover the tested environment
and reference data; validate the workflows with your own inputs before using
the results in research or operational work.
