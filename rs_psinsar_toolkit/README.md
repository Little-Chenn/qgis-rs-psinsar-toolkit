# Remote Sensing and PS-InSAR Processing & Mapping Toolkit

**English** | [简体中文](README_zh-CN.md)

Plugin ID: `rs_psinsar_toolkit`  
Candidate version: `0.3.0-rc1`  
Frozen release baseline: `0.2.3`  
Author: Yang Chenxi (杨晨曦)  
Affiliation: Xiamen University Joint Remote Sensing Receiving Station
(厦门大学联合遥感接收站)  
Contact: cyang5533@gmail.com  
Status: experimental bilingual pre-release candidate under local requalification

## Overview

This QGIS plugin integrates six workflows for external-GCP image-to-map correction,
SAR intensity processing and mapping in dB, and PS-InSAR product mapping and
descriptive time-series review. Every run uses read-only inputs and creates an
isolated output directory. Existing inputs and earlier products are not overwritten.

The plugin interface follows the QGIS language. Simplified Chinese is the source and
fallback language; English is loaded from the compiled Qt translation catalog.
Machine-facing field names, JSON keys, status values, formulas, output directory names,
and filenames remain identical in both languages.

## Modules

### 1. GCP-based Geometric Correction and Accuracy Assessment

- Uses external training ground control points for first-order affine,
  second-/third-order polynomial, or Thin Plate Spline transformation.
- Accepts a separate set of independent check points and reports training residuals
  and independent-check RMSE separately.
- Supports standard CSV and QGIS Georeferencer `.points` fields.
- Allows target CRS, automatic or explicit resolution, resampling, and an optional
  RMSE threshold.
- Produces a corrected GeoTIFF, copied control-point files, residual tables, a QA
  preview, and JSON/Markdown reports.
- This is external-GCP image-to-map geometric correction. It does not use SAR orbit,
  sensor-model, or DEM information and is not Range-Doppler terrain correction.

### 2. SAR Image Mosaicking, Mask Clipping and Display Enhancement

- Recursively scans ORG product directories and reads available XML,
  `manifest.safe`, and KML companion metadata.
- Supports single or multiple single-band GeoTIFF scenes and a same-CRS
  Polygon/MultiPolygon clipping mask.
- Checks acquisition direction, scene order, overlap, intensity-scale consistency,
  estimated pixels, memory, and disk requirements before processing.
- Applies ordered mosaicking, mask clipping, and `10 * log10(linear_power)`.
- Records finite, negative, and zero linear-power pixel counts before dB conversion.
- Provides percentile, minimum–maximum, mean–standard-deviation, histogram
  equalization, and mean-centered ±3σ display methods.
- Can create a separate RGBA 8-bit grayscale or single-band pseudocolor display
  product, with optional outer-edge feathering.
- Display enhancement never modifies the Float32 linear-power or dB scientific raster.
- Without complete Sigma0/Gamma0 calibration evidence, outputs are described only as
  `SAR intensity (dB)`, not calibrated backscatter.

### 3. SAR Intensity Mapping in dB

- Reads an existing single-band SAR intensity GeoTIFF in dB without repeating
  mosaicking, clipping, or logarithmic conversion.
- Creates a portable run containing an editable QGZ project, PNG/PDF maps, and a QA
  report.
- Uses the reviewed A3 portrait QPT derivative and an independent grayscale color bar.
- Supports optional coordinate reference system, spatial resolution, display method,
  data source, acquisition time, production date, and producing organization text.
- Uses the 2nd–98th display percentiles without altering source dB pixel values.

### 4. PS-InSAR Vertical Displacement Rate Mapping

- Uses a quality-controlled polygon-grid layer with a numeric `velocity` field.
- Accepts a layer already loaded in QGIS or a layer from a GeoPackage.
- Supports a local raster basemap, a current-project raster/XYZ basemap, or no basemap.
- Produces an editable QGZ project, PNG/PDF maps, and a QA report.
- The rate unit is `mm/year`; positive values indicate upward motion and negative
  values indicate downward motion.
- The module maps supplied rate values. It does not recompute rates or automatically
  identify anomalous values or physical causes.

### 5. Batch Mapping of PS-InSAR Cumulative Displacement

- Reads `ps_timeseries_points` and `time_catalog` from a compatible multi-temporal
  GeoPackage in read-only mode.
- Selects all epochs after the reference epoch by default. The zero-valued D0 map is
  optional and disabled by default.
- Calculates the pointwise difference `D_target - D_initial` first, then calculates
  the median of valid differences in each 50 m grid cell.
- Uses millimetres, with positive values indicating upward motion and negative values
  indicating downward motion.
- Uses common outer class boundaries of −20 mm and 20 mm for cross-epoch comparison.
- Produces one editable multi-layout QGZ project, per-epoch PNG/PDF maps, and QA reports.
- Does not create or overlay an extreme-point layer.

For the reviewed 56-epoch reference dataset, the default output is 55 cumulative
displacement maps because the initial epoch is used as the reference.

### 6. PS-InSAR Multi-point Displacement Time-series Review

- Queries a compatible multi-temporal GeoPackage by `ps_uid` without loading the
  complete multi-million-point layer into QGIS.
- Reviews ranked point lists in their defined order, plain `ps_uid` lists in file
  order, or complete candidate tables through controlled A/B × LOW/HIGH sampling.
- The default complete-candidate sample uses 12 points per stratum and 500 m global
  minimum spacing; class C remains in the candidate table but is not selected by
  default.
- Produces a time-series long table, point summary, editable point GeoPackage,
  overview PNG, detail PDF, and QA report.
- Displacement is in millimetres; positive values indicate upward motion and negative
  values indicate downward motion.
- Results are descriptive evidence for manual review only. The module does not
  automatically identify anomalies, classify trends, or infer physical causes.

## Safety and scientific contracts

- Inputs are read-only; each run uses a new timestamped directory.
- `CREATED`, `RUNNING`, `PASS`, `REVIEW`, `FAILED`, and `CANCELLED` remain
  machine-readable status values where applicable.
- Data fields such as `ps_uid`, `v_median`, and date fields are not translated.
- JSON schemas, formulas, aggregation order, thresholds, and sorting/sampling logic
  are language-independent.
- Scientific rasters and 8-bit display products remain separate.
- Failed or cancelled runs are retained for diagnosis and are not formal products.

## Requirements and documentation

The validated baseline and RC3 package passed QGIS `3.44.11` fresh installation,
39 automated tests, bilingual six-module regression, numeric comparison, thematic-map
regression, and manual acceptance. The `0.3.0-rc1` version and licensing promotion is
being requalified locally before publication.

- [Installation and short acceptance](INSTALL.md)
- [User guide](USER_GUIDE.md)
- [Release notes](RELEASE_NOTES.md)
- [Chinese README](README_zh-CN.md)

## License and attribution

Software source, QPT templates, Qt catalogs, SVG assets, and runtime resources are
licensed under `GPL-2.0-or-later`. English and Simplified Chinese documentation is
licensed under `CC BY 4.0`. The complete license files are distributed with the
repository and release package.

Copyright (C) 2026 Yang Chenxi (杨晨曦). The affiliation identifies the author's
stated institutional affiliation and does not by itself imply institutional ownership
or endorsement.

The planned public repository URL is
<https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit>. A local formal
`0.3.0-rc1` ZIP may be generated for requalification, but no GitHub repository
connection, upload, or public release is authorized by this statement.
