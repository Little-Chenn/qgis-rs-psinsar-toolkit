# User Guide

**English** | [简体中文](USER_GUIDE_zh-CN.md)

## 1. Task Center

Open **Remote Sensing and PS-InSAR Processing & Mapping Toolkit** from the QGIS
plugin menu or toolbar. The Task Center contains six modules:

1. GCP-based Geometric Correction and Accuracy Assessment;
2. SAR Image Mosaicking, Mask Clipping and Display Enhancement;
3. SAR Intensity Mapping in dB;
4. PS-InSAR Vertical Displacement Rate Mapping;
5. Batch Mapping of PS-InSAR Cumulative Displacement;
6. PS-InSAR Multi-point Displacement Time-series Review.

The plugin language follows the QGIS interface language. Restart QGIS after changing
the QGIS locale so that all plugin text and the matching bundled QPT templates are
loaded consistently.

## 2. General safety rules

- Select an existing output root. The plugin creates a new timestamped subdirectory.
- Source data and existing outputs are never deleted, moved, or overwritten.
- A failed or cancelled run is retained for diagnosis and is not a formal product.
- Keep each complete run directory together. Moving only the QGZ may break relative
  links to copied data, templates, or assets.
- Editable QGZ layouts can be refined manually in QGIS after generation.
- Display stretches and colors do not change scientific raster values.
- Output directory names, filenames, JSON keys, data fields, and status values do not
  change with the interface language.

## 3. GCP-based Geometric Correction and Accuracy Assessment

The default tab performs external-GCP image-to-map correction. A separate set of
independent check points is used to calculate check-point RMSE.

1. Select the raster to correct.
2. Select the training-GCP file and the independent-check-point file.
3. Enter a target CRS, for example `EPSG:32650`.
4. Select first-order affine, second-/third-order polynomial, or Thin Plate Spline.
5. Keep output resolution on automatic, or enter both X and Y resolution values.
6. Choose a resampling method appropriate for the data type.
7. Set the RMSE threshold to zero to report results for human assessment without an
   automatic accuracy pass/fail threshold.
8. Read and accept the stated scientific scope.
9. Check the settings, then run the task.

Standard CSV headers are `point_id,pixel,line,x,y`. The pixel/line origin is the
upper-left corner and line increases downward. QGIS Georeferencer `.points` fields are
also supported. If all `sourceY` values are negative, the plugin converts them to the
positive-down GDAL line convention.

Outputs include `01_控制点`, `02_校正成果`, `03_质量检查`, and `04_报告`.
These compatibility directory names remain unchanged in the English interface.
Independent-check RMSE is scientifically meaningful only when the check points are
independent of the training GCPs and come from a reliable external reference.

The **Workflow Validation** tab tests the control-point, RMSE, and report chain by
creating derived validation data. It validates the software workflow and does not
represent real manual-registration accuracy.

This module does not use SAR orbit, sensor-model, or DEM information and cannot replace
strict Range-Doppler terrain correction in software such as SNAP.

## 4. SAR Image Mosaicking, Mask Clipping and Display Enhancement

Inputs must be single-band, non-negative, linear-power GeoTIFFs. The clipping layer
must be a same-CRS Polygon or MultiPolygon. You may select an ORG root directory for
recursive discovery of TIFF, XML, `manifest.safe`, and KML companions, or process a
single scene.

1. Scan the images and explicitly review their coverage order. If the ORG directory
   contains different acquisition directions, retain ascending-only or descending-only
   scenes unless there is a justified reason to mix them.
2. Select the clipping mask and an existing output root.
3. Set target resolution and resampling. Nearest Neighbour is recommended for linear
   power. Cubic Convolution requires a separate risk acknowledgement because it can
   produce non-physical negative values.
4. Select a display method, brightness/contrast/Gamma settings, and grayscale or
   single-band pseudocolor.
5. Keep the separate 8-bit display product enabled when needed. Basic outer-edge
   feathering is disabled by default.
6. Confirm that the input contains linear power suitable for `10 * log10` and, for
   multiple scenes, confirm the coverage order.
7. If mixed acquisition directions or a within-group median-intensity deviation above
   6 dB is reported, inspect the products before explicitly accepting the risk.
8. Review the mask-intersection resource estimate, then run.

Processing uses a common grid, ordered mosaicking, mask clipping, and linear-power-to-dB
conversion, followed by an optional independent 8-bit display product. The module does
not perform automatic seamline generation or physical radiometric balancing. NaN edges
without declared NoData are protected with a read-only temporary VRT so that later
scenes do not hide earlier valid pixels.

If the metadata does not provide complete Sigma0/Gamma0 calibration evidence, the
output is labelled `SAR intensity (dB)`, not calibrated backscatter. Pseudocolor for a
single VV band does not represent true ground-object color.

## 5. SAR Intensity Mapping in dB

The input must be a reviewed single-band GeoTIFF in dB. This module does not repeat
mosaicking, clipping, or `10 * log10` conversion.

1. Select the SAR intensity GeoTIFF in dB and an output root.
2. Select **Read Image Information**.
3. Set the map title and the seven optional information fields.
4. Review automatic wrapping in the right-side preview; the maximum is eight lines.
5. Select QGZ, PNG, PDF, and the required DPI.
6. Check the settings, then generate the map.

The output contains a portable copy of the dB raster, an editable QGZ, PNG/PDF maps,
and a QA report. The grayscale color bar is independent of the raster legend and uses
the 2nd–98th display percentiles. These display limits do not modify source pixels.

## 6. PS-InSAR Vertical Displacement Rate Mapping

The input is a polygon-grid layer containing a numeric velocity field. You may use a
layer already loaded in the current project or select a GeoPackage layer. The basemap
may be a local raster, a raster/XYZ layer from the project, or none.

1. Select the input mode and velocity layer.
2. Select or enter the numeric velocity field.
3. Select the basemap mode and source.
4. Select an existing output root.
5. Set the title and optional map-production information.
6. Select QGZ, PNG, PDF, and DPI; check the settings, then generate the map.

The accepted semantics are `mm/year`, positive upward and negative downward. The
module maps existing rate values; it does not recompute them or automatically identify
anomalies or their causes. Verify units and sign convention when using other datasets.

## 7. Batch Mapping of PS-InSAR Cumulative Displacement

The input must be a compatible multi-temporal GeoPackage containing
`ps_timeseries_points` and `time_catalog`. The plugin opens it read-only.

1. Select the GeoPackage and scan the epoch catalog in read-only mode.
2. All later epochs are selected by default. Enable the D0 map only if a zero-valued
   reference map is required.
3. Select a local satellite-imagery basemap and an existing output root.
4. Leave the template field empty to use the reviewed bundled template, or select a
   compatible external QPT.
5. Set the title pattern, data source, monitoring period, production date, and
   producing organization.
6. Select QGZ, PNG, PDF, and DPI; check the settings, then run.

The calculation order is fixed: calculate `D_target - D_initial` for each PS point,
then calculate the median of valid differences in every 50 m grid cell. The unit is mm;
positive values indicate upward motion and negative values indicate downward motion.
All epochs use common outer class boundaries of −20 mm and 20 mm. No extreme-point layer
is created.

The run contains:

- `data/cumulative_displacement_grid.gpkg`: multi-epoch wide grid with shared geometry;
- `project/ps_insar_cumulative_displacement_batch.qgz`: editable multi-layout project;
- `maps/png` and `maps/pdf`: one map per selected epoch;
- `qa`: overall report, per-epoch PASS records, and task status.

Cancellation takes effect after the current batch and retains the cancellation state
and temporary work. Resume-in-place is not supported; rerunning creates a new run.

## 8. PS-InSAR Multi-point Displacement Time-series Review

Inputs are a compatible multi-temporal GeoPackage and a point CSV. The GeoPackage must
contain `ps_timeseries_points` and `time_catalog`; the CSV must contain at least
`ps_uid`.

1. Select the multi-temporal GeoPackage, point CSV, and an existing output root.
2. Inspect inputs in read-only mode and verify point count, epoch range, and unit mm.
3. A list containing `selection_rank` is reviewed in its defined order. A complete
   candidate table uses controlled sampling with 12 points in each A/B × LOW/HIGH
   stratum and 500 m global minimum spacing by default.
4. Select CSV, point GeoPackage, overview PNG, and detail PDF outputs.
5. Check the settings and run. The result layer can be loaded and zoomed to on
   completion.

For complete candidate tables, the default 48-point sample balances A/B × LOW/HIGH;
class C is excluded from the default sample. Outputs use the stable directories
`01_数据表`, `02_点位图层`, `03_图表`, and `04_质量报告`. Displacement is in mm,
positive upward and negative downward. Curves and statistics support manual review
only; they do not automatically identify anomalies or establish physical causes. The
per-run maximum is 200 points to keep the detail PDF manageable.

## 9. Troubleshooting

- **Blank map:** check the input CRS, layer extent, and project CRS.
- **All-black SAR result:** verify that the source is linear power and that the display
  range is appropriate.
- **Clipped or overflowing text:** shorten optional map text and inspect the preview.
- **Missing QGZ resources:** move or archive the complete run directory, not only QGZ.
- **Failed task:** keep the run and logs, then inspect the failure or QA report.
