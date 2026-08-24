"""Core functions for the non-destructive geometry-correction teaching demo."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
from osgeo import gdal, osr

from .localization import tr
from .version import GEOMETRY_ENGINE_VERSION


VERSION = GEOMETRY_ENGINE_VERSION
PURPOSE = "registration_teaching_mode_only"
PIXEL_CONVENTION = (
    "pixel and line are GDAL raster coordinates of pixel centres; "
    "integer pixel_index/line_index are zero-based array indices, so "
    "pixel=pixel_index+0.5 and line=line_index+0.5"
)

gdal.UseExceptions()

CancelCallback = Callable[[], bool] | None
ProgressCallback = Callable[[int, str], None] | None
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


class GeometryCancelled(RuntimeError):
    """Raised when a cooperative geometry task cancellation is observed."""


def _check_cancelled(is_cancelled: CancelCallback) -> None:
    if is_cancelled is not None and is_cancelled():
        raise GeometryCancelled(_tr("用户取消了几何校正任务。"))


def _progress(
    callback: ProgressCallback,
    value: int,
    message: str,
) -> None:
    if callback is not None:
        callback(max(0, min(100, int(value))), message)


@dataclass(frozen=True)
class ControlPoint:
    point_id: str
    grid_row: int
    grid_col: int
    subset: str
    pixel_index: int
    line_index: int
    pixel: float
    line: float
    x: float
    y: float
    coordinate_convention: str = PIXEL_CONVENTION
    source: str = "reference_geotransform"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def _authority_code(wkt: str) -> str | None:
    if not wkt:
        return None
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    srs.AutoIdentifyEPSG()
    authority = srs.GetAuthorityName(None)
    code = srs.GetAuthorityCode(None)
    return f"{authority}:{code}" if authority and code else None


def _dataset_geotransform(dataset: gdal.Dataset) -> tuple[float, ...] | None:
    try:
        value = dataset.GetGeoTransform(can_return_null=True)
    except TypeError:  # Compatibility with older GDAL Python wrappers.
        value = dataset.GetGeoTransform()
        if value == (0.0, 1.0, 0.0, 0.0, 0.0, 1.0):
            return None
    return tuple(float(item) for item in value) if value is not None else None


def inspect_raster(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Raster not found: {path}")
    dataset = gdal.OpenEx(str(path), gdal.OF_RASTER | gdal.OF_READONLY)
    if dataset is None:
        raise RuntimeError(f"GDAL cannot open raster: {path}")
    band = dataset.GetRasterBand(1) if dataset.RasterCount else None
    projection = dataset.GetProjectionRef() or ""
    result = {
        "path": str(path),
        "driver": dataset.GetDriver().ShortName,
        "width": dataset.RasterXSize,
        "height": dataset.RasterYSize,
        "band_count": dataset.RasterCount,
        "band_type": gdal.GetDataTypeName(band.DataType) if band else None,
        "nodata": band.GetNoDataValue() if band else None,
        "projection_wkt": projection,
        "crs": _authority_code(projection),
        "geotransform": _dataset_geotransform(dataset),
        "gcp_count": dataset.GetGCPCount(),
        "size_bytes": path.stat().st_size,
        "modified_utc": datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds"),
        "sha256": sha256_file(path),
    }
    dataset = None
    return result


def validate_reference_raster(path: Path) -> dict[str, Any]:
    info = inspect_raster(path)
    problems: list[str] = []
    if info["driver"] != "GTiff":
        problems.append(f"expected GTiff, got {info['driver']}")
    if info["band_count"] != 1:
        problems.append(f"expected one band, got {info['band_count']}")
    if info["band_type"] != "Byte":
        problems.append(f"expected Byte, got {info['band_type']}")
    if info["crs"] != "EPSG:4326":
        problems.append(f"expected EPSG:4326, got {info['crs']}")
    geotransform = info["geotransform"]
    if geotransform is None:
        problems.append("reference raster has no geotransform")
    elif not math.isclose(geotransform[2], 0.0, abs_tol=1e-15) or not math.isclose(
        geotransform[4], 0.0, abs_tol=1e-15
    ):
        problems.append("rotated reference geotransforms are outside this baseline demo")
    if info["width"] <= 1 or info["height"] <= 1:
        problems.append("raster dimensions are too small")
    if problems:
        raise ValueError("Reference raster preflight failed: " + "; ".join(problems))
    return info


def environment_manifest() -> dict[str, Any]:
    return {
        "python": sys.version.replace("\n", " "),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "gdal": gdal.VersionInfo("--version"),
        "numpy": np.__version__,
        "script_version": VERSION,
    }


def ensure_new_run_directory(output_root: Path, run_id: str) -> Path:
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / run_id
    if run_dir.exists():
        raise FileExistsError(
            f"Run directory already exists; choose a different run-id: {run_dir}"
        )
    free_bytes = shutil.disk_usage(output_root).free
    if free_bytes < 512 * 1024 * 1024:
        raise OSError(
            f"Less than 512 MiB free at output root ({free_bytes} bytes): {output_root}"
        )
    run_dir.mkdir()
    return run_dir


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def export_unreferenced_png(
    source_path: Path,
    output_path: Path,
    *,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    _check_cancelled(is_cancelled)
    source = gdal.OpenEx(str(source_path), gdal.OF_RASTER | gdal.OF_READONLY)
    if source is None:
        raise RuntimeError(f"Cannot open source raster: {source_path}")
    if source.RasterCount != 1 or source.GetRasterBand(1).DataType != gdal.GDT_Byte:
        raise ValueError("Baseline PNG export requires a single-band Byte source")
    memory = gdal.GetDriverByName("MEM").Create(
        "", source.RasterXSize, source.RasterYSize, 1, gdal.GDT_Byte
    )
    source_band = source.GetRasterBand(1)
    target_band = memory.GetRasterBand(1)
    block_rows = 512
    for y_offset in range(0, source.RasterYSize, block_rows):
        _check_cancelled(is_cancelled)
        row_count = min(block_rows, source.RasterYSize - y_offset)
        array = source_band.ReadAsArray(0, y_offset, source.RasterXSize, row_count)
        target_band.WriteArray(array, 0, y_offset)
        _progress(
            progress,
            int(100 * (y_offset + row_count) / source.RasterYSize),
            _tr("正在导出无地理信息PNG……"),
        )
    target_band.FlushCache()
    output = gdal.GetDriverByName("PNG").CreateCopy(str(output_path), memory, strict=1)
    if output is None:
        raise RuntimeError(f"PNG export failed: {output_path}")
    output.FlushCache()
    output = None
    memory = None
    source = None
    _check_cancelled(is_cancelled)

    info = inspect_raster(output_path)
    if info["projection_wkt"] or info["geotransform"] is not None or info["gcp_count"]:
        raise RuntimeError("Exported PNG unexpectedly contains spatial reference information")
    if Path(f"{output_path}.aux.xml").exists():
        raise RuntimeError("Exported PNG unexpectedly has a georeferencing aux.xml sidecar")
    return info


def apply_geotransform(
    geotransform: Sequence[float], pixel: float, line: float
) -> tuple[float, float]:
    x = geotransform[0] + pixel * geotransform[1] + line * geotransform[2]
    y = geotransform[3] + pixel * geotransform[4] + line * geotransform[5]
    return float(x), float(y)


def _grid_indices(size: int, count: int) -> list[int]:
    if count < 2:
        raise ValueError("Grid count must be at least two")
    values = np.rint(np.linspace(0, size - 1, count)).astype(int).tolist()
    if len(set(values)) != count:
        raise ValueError(f"Raster dimension {size} is too small for a {count}-point grid")
    return values


def generate_control_points(
    width: int,
    height: int,
    geotransform: Sequence[float],
    grid_size: int = 5,
) -> list[ControlPoint]:
    columns = _grid_indices(width, grid_size)
    rows = _grid_indices(height, grid_size)
    points: list[ControlPoint] = []
    for grid_row, line_index in enumerate(rows):
        for grid_col, pixel_index in enumerate(columns):
            pixel = pixel_index + 0.5
            line = line_index + 0.5
            x, y = apply_geotransform(geotransform, pixel, line)
            subset = "train" if (grid_row + grid_col) % 2 == 0 else "check"
            points.append(
                ControlPoint(
                    point_id=f"G{grid_row + 1}{grid_col + 1}",
                    grid_row=grid_row + 1,
                    grid_col=grid_col + 1,
                    subset=subset,
                    pixel_index=pixel_index,
                    line_index=line_index,
                    pixel=pixel,
                    line=line,
                    x=x,
                    y=y,
                )
            )
    validate_control_point_split(points)
    return points


def validate_control_point_split(points: Sequence[ControlPoint]) -> None:
    train = [point for point in points if point.subset == "train"]
    check = [point for point in points if point.subset == "check"]
    if len(train) < 6 or len(check) < 8:
        raise ValueError(
            f"Insufficient split: train={len(train)}, check={len(check)}"
        )
    train_ids = {point.point_id for point in train}
    check_ids = {point.point_id for point in check}
    if train_ids & check_ids:
        raise ValueError("Training and check point IDs overlap")
    train_pixels = {(point.pixel, point.line) for point in train}
    check_pixels = {(point.pixel, point.line) for point in check}
    if train_pixels & check_pixels:
        raise ValueError("Training and check pixel coordinates overlap")


CONTROL_POINT_FIELDS = [field.name for field in ControlPoint.__dataclass_fields__.values()]


def write_control_points(path: Path, points: Iterable[ControlPoint]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CONTROL_POINT_FIELDS)
        writer.writeheader()
        for point in points:
            writer.writerow(asdict(point))


def fit_affine(points: Sequence[ControlPoint]) -> dict[str, Any]:
    if len(points) < 3:
        raise ValueError("At least three points are required for an affine fit")
    design = np.asarray([[1.0, p.pixel, p.line] for p in points], dtype=np.float64)
    targets = np.asarray([[p.x, p.y] for p in points], dtype=np.float64)
    coefficients, _residuals, rank, singular_values = np.linalg.lstsq(
        design, targets, rcond=None
    )
    if rank != 3:
        raise ValueError(f"Affine design matrix rank is {rank}, expected 3")
    condition_number = float(np.linalg.cond(design))
    return {
        "coefficients": coefficients,
        "rank": int(rank),
        "singular_values": singular_values.tolist(),
        "condition_number": condition_number,
        "geotransform": [
            float(coefficients[0, 0]),
            float(coefficients[1, 0]),
            float(coefficients[2, 0]),
            float(coefficients[0, 1]),
            float(coefficients[1, 1]),
            float(coefficients[2, 1]),
        ],
    }


def _map_delta_to_pixel_delta(
    geotransform: Sequence[float], dx: float, dy: float
) -> tuple[float, float]:
    matrix = np.asarray(
        [[geotransform[1], geotransform[2]], [geotransform[4], geotransform[5]]],
        dtype=np.float64,
    )
    pixel_line = np.linalg.solve(matrix, np.asarray([dx, dy], dtype=np.float64))
    return float(pixel_line[0]), float(pixel_line[1])


def _coordinate_transform(source_epsg: int, target_epsg: int) -> osr.CoordinateTransformation:
    source = osr.SpatialReference()
    source.ImportFromEPSG(source_epsg)
    target = osr.SpatialReference()
    target.ImportFromEPSG(target_epsg)
    if hasattr(source, "SetAxisMappingStrategy"):
        source.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(source, target)


def calculate_residuals(
    points: Sequence[ControlPoint],
    coefficients: np.ndarray,
    reference_geotransform: Sequence[float],
    metric_epsg: int = 32650,
) -> tuple[list[dict[str, Any]], dict[str, float | int]]:
    transform = _coordinate_transform(4326, metric_epsg)
    rows: list[dict[str, Any]] = []
    for point in points:
        vector = np.asarray([1.0, point.pixel, point.line], dtype=np.float64)
        predicted = vector @ coefficients
        predicted_x = float(predicted[0])
        predicted_y = float(predicted[1])
        dx = predicted_x - point.x
        dy = predicted_y - point.y
        error_2d = math.hypot(dx, dy)
        expected_m = transform.TransformPoint(point.x, point.y)
        predicted_m = transform.TransformPoint(predicted_x, predicted_y)
        dx_m = float(predicted_m[0] - expected_m[0])
        dy_m = float(predicted_m[1] - expected_m[1])
        error_m = math.hypot(dx_m, dy_m)
        d_pixel, d_line = _map_delta_to_pixel_delta(reference_geotransform, dx, dy)
        error_pixel = math.hypot(d_pixel, d_line)
        rows.append(
            {
                "point_id": point.point_id,
                "subset": point.subset,
                "pixel": point.pixel,
                "line": point.line,
                "expected_x": point.x,
                "expected_y": point.y,
                "predicted_x": predicted_x,
                "predicted_y": predicted_y,
                "dx_degree": dx,
                "dy_degree": dy,
                "error_2d_degree": error_2d,
                "dx_m": dx_m,
                "dy_m": dy_m,
                "error_m": error_m,
                "d_pixel": d_pixel,
                "d_line": d_line,
                "error_pixel": error_pixel,
            }
        )
    metrics = residual_metrics(rows)
    return rows, metrics


def residual_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, float | int]:
    if not rows:
        raise ValueError("Residual rows are empty")

    def rmse(name: str) -> float:
        return float(math.sqrt(np.mean([float(row[name]) ** 2 for row in rows])))

    return {
        "point_count": len(rows),
        "rmse_x_degree": rmse("dx_degree"),
        "rmse_y_degree": rmse("dy_degree"),
        "rmse_2d_degree": float(
            math.sqrt(np.mean([float(row["error_2d_degree"]) ** 2 for row in rows]))
        ),
        "rmse_x_m": rmse("dx_m"),
        "rmse_y_m": rmse("dy_m"),
        "rmse_2d_m": float(
            math.sqrt(np.mean([float(row["error_m"]) ** 2 for row in rows]))
        ),
        "mean_absolute_error_m": float(np.mean([row["error_m"] for row in rows])),
        "max_error_m": float(max(row["error_m"] for row in rows)),
        "rmse_pixel": float(
            math.sqrt(np.mean([float(row["error_pixel"]) ** 2 for row in rows]))
        ),
        "max_error_pixel": float(max(row["error_pixel"] for row in rows)),
    }


def write_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def georeference_png(
    png_path: Path,
    output_path: Path,
    training_points: Sequence[ControlPoint],
    reference_info: dict[str, Any],
    run_id: str,
    resampling: str = "bilinear",
    *,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    _check_cancelled(is_cancelled)
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")
    partial_path = output_path.with_name(f".{output_path.stem}.partial.tif")
    if partial_path.exists():
        raise FileExistsError(f"Partial output already exists: {partial_path}")
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    if hasattr(srs, "SetAxisMappingStrategy"):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    gcps = [
        gdal.GCP(point.x, point.y, 0.0, point.pixel, point.line)
        for point in training_points
    ]
    vrt_path = f"/vsimem/geometry-correction-{os.getpid()}-{run_id}.vrt"
    translated = gdal.Translate(
        vrt_path,
        str(png_path),
        options=gdal.TranslateOptions(
            format="VRT", GCPs=gcps, outputSRS=srs.ExportToWkt()
        ),
    )
    if translated is None:
        raise RuntimeError("Failed to attach training GCPs to the PNG")
    translated.FlushCache()
    translated = None

    geotransform = reference_info["geotransform"]
    width = int(reference_info["width"])
    height = int(reference_info["height"])
    xmin = geotransform[0]
    ymax = geotransform[3]
    xmax = geotransform[0] + width * geotransform[1]
    ymin = geotransform[3] + height * geotransform[5]
    def warp_progress(fraction, message, _data):
        _progress(
            progress,
            int(float(fraction) * 100),
            message or _tr("正在执行GCP Warp……"),
        )
        return 0 if is_cancelled is not None and is_cancelled() else 1

    try:
        try:
            warped = gdal.Warp(
                str(partial_path),
                vrt_path,
                options=gdal.WarpOptions(
                    format="GTiff",
                    dstSRS="EPSG:4326",
                    outputBounds=(xmin, ymin, xmax, ymax),
                    outputBoundsSRS="EPSG:4326",
                    width=width,
                    height=height,
                    polynomialOrder=1,
                    errorThreshold=0.0,
                    resampleAlg=resampling,
                    multithread=True,
                    callback=warp_progress,
                    creationOptions=[
                        "COMPRESS=LZW",
                        "TILED=YES",
                        "BIGTIFF=IF_SAFER",
                    ],
                ),
            )
        except RuntimeError as exc:
            if is_cancelled is not None and is_cancelled():
                raise GeometryCancelled(
                    _tr("用户在GCP Warp过程中取消了任务。")
                ) from exc
            raise
    finally:
        gdal.Unlink(vrt_path)
    _check_cancelled(is_cancelled)
    if warped is None:
        raise RuntimeError("GDAL GCP Warp failed")
    warped.SetMetadataItem("PURPOSE", PURPOSE)
    warped.SetMetadataItem("SCRIPT_VERSION", VERSION)
    warped.SetMetadataItem("RUN_ID", run_id)
    warped.SetMetadataItem("SOURCE_SHA256", reference_info["sha256"])
    warped.SetMetadataItem("METHOD", "training GCPs; first-order polynomial")
    warped.SetMetadataItem("RESAMPLING", resampling)
    warped.SetMetadataItem("PIXEL_CONVENTION", PIXEL_CONVENTION)
    warped.SetMetadataItem("TRAINING_POINT_COUNT", str(len(training_points)))
    warped.FlushCache()
    warped = None
    partial_info = inspect_raster(partial_path)
    if partial_info["crs"] != "EPSG:4326":
        raise RuntimeError(f"Unexpected output CRS: {partial_info['crs']}")
    if (partial_info["width"], partial_info["height"]) != (width, height):
        raise RuntimeError("Output raster dimensions do not match the reference")
    partial_path.replace(output_path)
    return inspect_raster(output_path)


def compare_rasters(
    reference_path: Path,
    restored_path: Path,
    preview_path: Path,
    max_preview_dimension: int = 1400,
    *,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    _check_cancelled(is_cancelled)
    reference = gdal.OpenEx(str(reference_path), gdal.OF_RASTER | gdal.OF_READONLY)
    restored = gdal.OpenEx(str(restored_path), gdal.OF_RASTER | gdal.OF_READONLY)
    if reference is None or restored is None:
        raise RuntimeError("Could not open rasters for comparison")
    if (reference.RasterXSize, reference.RasterYSize) != (
        restored.RasterXSize,
        restored.RasterYSize,
    ):
        raise ValueError("Comparison requires equal raster dimensions")

    width = reference.RasterXSize
    height = reference.RasterYSize
    scale = min(1.0, max_preview_dimension / max(width, height))
    preview_width = max(1, int(round(width * scale)))
    preview_height = max(1, int(round(height * scale)))
    reference_preview = reference.GetRasterBand(1).ReadAsArray(
        buf_xsize=preview_width, buf_ysize=preview_height
    ).astype(np.float32)
    restored_preview = restored.GetRasterBand(1).ReadAsArray(
        buf_xsize=preview_width, buf_ysize=preview_height
    ).astype(np.float32)
    difference_preview = np.abs(reference_preview - restored_preview)

    count = 0
    sum_abs = 0.0
    sum_square = 0.0
    maximum = 0.0
    block_rows = 512
    for y_offset in range(0, height, block_rows):
        _check_cancelled(is_cancelled)
        row_count = min(block_rows, height - y_offset)
        first = reference.GetRasterBand(1).ReadAsArray(0, y_offset, width, row_count)
        second = restored.GetRasterBand(1).ReadAsArray(0, y_offset, width, row_count)
        delta = first.astype(np.float32) - second.astype(np.float32)
        absolute = np.abs(delta)
        count += int(delta.size)
        sum_abs += float(np.sum(absolute, dtype=np.float64))
        sum_square += float(np.sum(delta * delta, dtype=np.float64))
        maximum = max(maximum, float(np.max(absolute)))
        _progress(
            progress,
            int(75 * (y_offset + row_count) / height),
            _tr("正在比较参考影像与恢复影像……"),
        )

    _check_cancelled(is_cancelled)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimSun",
        "Noto Sans CJK SC",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False

    # The source quick-look has no explicit NoData value.  Treat only zero-valued
    # pixels connected to the preview boundary as the outer footprint so valid
    # dark pixels inside the scene remain visible.
    from collections import deque

    common_zero = (reference_preview == 0) & (restored_preview == 0)
    outer_background = np.zeros(common_zero.shape, dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x_index in range(preview_width):
        if common_zero[0, x_index]:
            queue.append((0, x_index))
        if common_zero[preview_height - 1, x_index]:
            queue.append((preview_height - 1, x_index))
    for y_index in range(preview_height):
        if common_zero[y_index, 0]:
            queue.append((y_index, 0))
        if common_zero[y_index, preview_width - 1]:
            queue.append((y_index, preview_width - 1))
    while queue:
        y_index, x_index = queue.popleft()
        if outer_background[y_index, x_index] or not common_zero[y_index, x_index]:
            continue
        outer_background[y_index, x_index] = True
        if y_index > 0:
            queue.append((y_index - 1, x_index))
        if y_index + 1 < preview_height:
            queue.append((y_index + 1, x_index))
        if x_index > 0:
            queue.append((y_index, x_index - 1))
        if x_index + 1 < preview_width:
            queue.append((y_index, x_index + 1))

    reference_display = np.ma.masked_where(outer_background, reference_preview)
    restored_display = np.ma.masked_where(outer_background, restored_preview)
    difference_display = np.ma.masked_where(outer_background, difference_preview)
    gray_cmap = plt.get_cmap("gray").copy()
    gray_cmap.set_bad("#E5E7EB")
    difference_cmap = plt.get_cmap("magma").copy()
    difference_cmap.set_bad("#E5E7EB")

    tile = max(16, min(preview_width, preview_height) // 12)
    yy, xx = np.indices(reference_preview.shape)
    use_reference = ((xx // tile) + (yy // tile)) % 2 == 0
    checkerboard = np.ma.masked_where(
        outer_background,
        np.where(use_reference, reference_preview, restored_preview),
    )
    figure = plt.figure(figsize=(15, 11.2), facecolor="white")
    grid = figure.add_gridspec(2, 2, left=0.035, right=0.93, bottom=0.075,
                               top=0.89, wspace=0.035, hspace=0.10)
    axes = np.asarray(
        [
            [figure.add_subplot(grid[0, 0]), figure.add_subplot(grid[0, 1])],
            [figure.add_subplot(grid[1, 0]), figure.add_subplot(grid[1, 1])],
        ],
        dtype=object,
    )
    axes[0, 0].imshow(reference_display, cmap=gray_cmap, vmin=0, vmax=255)
    axes[0, 0].set_title(_tr("参考影像（GeoTIFF）"), fontsize=13, pad=8)
    axes[0, 1].imshow(restored_display, cmap=gray_cmap, vmin=0, vmax=255)
    axes[0, 1].set_title(_tr("空间参考恢复结果（GeoTIFF）"), fontsize=13, pad=8)
    axes[1, 0].imshow(checkerboard, cmap=gray_cmap, vmin=0, vmax=255)
    axes[1, 0].set_title(_tr("棋盘格叠加对比"), fontsize=13, pad=8)
    difference_display_max = max(1.0, float(np.max(difference_preview)))
    image = axes[1, 1].imshow(
        difference_display,
        cmap=difference_cmap,
        vmin=0.0,
        vmax=difference_display_max,
    )
    axes[1, 1].set_title(_tr("绝对像元差值（8位灰度）"), fontsize=13, pad=8)
    colorbar_visible = maximum > 0.0
    if colorbar_visible:
        color_axis = axes[1, 1].inset_axes([1.015, 0.03, 0.032, 0.94])
        colorbar = figure.colorbar(image, cax=color_axis)
        colorbar.set_label(_tr("绝对灰度差值"), fontsize=10)
        colorbar.ax.tick_params(labelsize=9)
    if maximum == 0.0:
        axes[1, 1].text(
            0.5,
            0.5,
            _tr("有效像元范围内无灰度差异\n最大绝对差：0\n灰度差异 RMSE：0"),
            transform=axes[1, 1].transAxes,
            horizontalalignment="center",
            verticalalignment="center",
            color="white",
            fontsize=12,
            bbox={
                "boxstyle": "round,pad=0.5",
                "facecolor": "black",
                "edgecolor": "white",
                "alpha": 0.72,
            },
        )
    for axis in axes.flat:
        axis.set_axis_off()
    figure.suptitle(_tr("几何校正结果对比与像元差异检查"), fontsize=18, y=0.975)
    figure.text(
        0.5,
        0.937,
        _tr("8位灰度预览；几何精度以独立检查点 RMSE 报告为准"),
        ha="center",
        va="center",
        fontsize=10.5,
        color="#444444",
    )
    figure.text(
        0.5,
        0.022,
        _tr("注：像元差异用于检查影像显示一致性，不替代独立检查点几何精度评价。"),
        ha="center",
        va="center",
        fontsize=9,
        color="#555555",
    )
    figure.canvas.draw()
    top_right_position = axes[0, 1].get_position().bounds
    bottom_right_position = axes[1, 1].get_position().bounds
    right_column_alignment_pass = (
        abs(top_right_position[0] - bottom_right_position[0]) < 1e-9
        and abs(top_right_position[2] - bottom_right_position[2]) < 1e-9
    )
    figure.savefig(preview_path, dpi=160)
    plt.close(figure)
    _progress(progress, 100, _tr("叠加比较图已生成。"))
    _check_cancelled(is_cancelled)
    reference = None
    restored = None
    return {
        "pixel_count": count,
        "mean_absolute_difference": sum_abs / count,
        "rmse_pixel_value": math.sqrt(sum_square / count),
        "max_absolute_difference": maximum,
        "preview_width": preview_width,
        "preview_height": preview_height,
        "layout": "2x2 aligned image axes; compact conditional colorbar",
        "top_right_axes": list(top_right_position),
        "bottom_right_axes": list(bottom_right_position),
        "right_column_alignment_pass": right_column_alignment_pass,
        "zero_difference_annotation": maximum == 0.0,
        "colorbar_visible": colorbar_visible,
    }


def geotransform_differences(
    reference: Sequence[float], restored: Sequence[float]
) -> dict[str, Any]:
    differences = [float(b - a) for a, b in zip(reference, restored)]
    return {
        "reference": list(reference),
        "restored": list(restored),
        "difference": differences,
        "max_absolute_difference": max(abs(value) for value in differences),
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    check = report["residuals"]["check"]
    train = report["residuals"]["train"]
    output = report["output"]
    comparison = report["raster_comparison"]
    template = _tr("""# 几何校正流程验证报告

运行 ID：`{run_id}`  
脚本版本：`{script_version}`  
状态：`{status}`

## 结论

- 已完成 `GeoTIFF → 无地理信息 PNG → 训练 GCP → 一阶多项式 GeoTIFF → 独立检查点 RMSE → 叠加比较`。
- 训练点 {train_count} 个，独立检查点 {check_count} 个，两组互斥。
- 独立检查二维 RMSE：`{check_rmse_m:.9f} m` / `{check_rmse_pixel:.9f} pixel`。
- 独立检查最大误差：`{check_max_m:.9f} m` / `{check_max_pixel:.9f} pixel`。
- 恢复影像与参考影像的像元值 RMSE：`{raster_rmse:.9f}`（Byte 灰度值）。

## 重要限制

本次 GCP 的地图坐标由原始 GeoTransform 自动生成，因此这是软件流程、像元坐标约定和可复现性的教学验证。理论误差应接近零，**不能代表人工选点或真实外部控制点条件下的配准精度**。源 TIFF 与 PNG 均为 Byte 快速预览，不用于替代原始浮点 SAR 定量数据。

## 输入

- 源文件：`{input_path}`
- SHA-256：`{input_sha256}`
- 尺寸：{input_width} × {input_height}
- 波段/类型：{band_count} / {band_type}
- CRS：{input_crs}
- GeoTransform：`{input_geotransform}`

## 方法

- 像元约定：{pixel_convention}
- 候选点：5×5 规则网格，共 {all_points} 个。
- 拆分方式：棋盘格；训练 {train_points} 个，检查 {check_points} 个。
- 模型：一阶二维仿射；仅训练点参与拟合和 GDAL Warp。
- 重采样：`{resampling}`。
- 输出网格：显式约束为参考影像的 CRS、范围、宽度和高度。

## 精度

| 指标 | 训练点 | 独立检查点 |
|---|---:|---:|
| 二维 RMSE（度） | {train_rmse_degree:.12g} | {check_rmse_degree:.12g} |
| 二维 RMSE（米，EPSG:32650） | {train_rmse_m:.9f} | {check_rmse_m:.9f} |
| RMSE（像素） | {train_rmse_pixel:.9f} | {check_rmse_pixel:.9f} |
| 最大误差（米） | {train_max_m:.9f} | {check_max_m:.9f} |
| 最大误差（像素） | {train_max_pixel:.9f} | {check_max_pixel:.9f} |

## 输出与对比

- 恢复 GeoTIFF：`{output_path}`
- 输出 CRS：{output_crs}
- 输出尺寸：{output_width} × {output_height}
- GeoTransform 最大绝对差：`{geotransform_max_difference:.12g}`
- 像元平均绝对差：`{mean_absolute_difference:.9f}`
- 像元最大绝对差：`{max_absolute_difference:.9f}`
- 叠加/差异图：`comparison_preview.png`

## 验收与保护

- 源 TIFF 运行前 SHA-256：`{source_sha256_before}`
- 源 TIFF 运行后 SHA-256：`{source_sha256_after}`
- 源文件未变化：`{source_unchanged}`
- PS-InSAR语义不参与本几何校正计算；项目已确认velocity单位为mm/年、
  displacement单位为mm，正值表示垂直向上，负值表示垂直向下。
""")
    return template.format(
        run_id=report["run_id"],
        script_version=report["script_version"],
        status=report["status"],
        train_count=train["point_count"],
        check_count=check["point_count"],
        check_rmse_m=check["rmse_2d_m"],
        check_rmse_pixel=check["rmse_pixel"],
        check_max_m=check["max_error_m"],
        check_max_pixel=check["max_error_pixel"],
        raster_rmse=comparison["rmse_pixel_value"],
        input_path=report["input"]["path"],
        input_sha256=report["input"]["sha256"],
        input_width=report["input"]["width"],
        input_height=report["input"]["height"],
        band_count=report["input"]["band_count"],
        band_type=report["input"]["band_type"],
        input_crs=report["input"]["crs"],
        input_geotransform=report["input"]["geotransform"],
        pixel_convention=report["pixel_convention"],
        all_points=report["control_points"]["all"],
        train_points=report["control_points"]["train"],
        check_points=report["control_points"]["check"],
        resampling=report["method"]["resampling"],
        train_rmse_degree=train["rmse_2d_degree"],
        check_rmse_degree=check["rmse_2d_degree"],
        train_rmse_m=train["rmse_2d_m"],
        train_rmse_pixel=train["rmse_pixel"],
        train_max_m=train["max_error_m"],
        train_max_pixel=train["max_error_pixel"],
        output_path=output["path"],
        output_crs=output["crs"],
        output_width=output["width"],
        output_height=output["height"],
        geotransform_max_difference=report["geotransform_comparison"][
            "max_absolute_difference"
        ],
        mean_absolute_difference=comparison["mean_absolute_difference"],
        max_absolute_difference=comparison["max_absolute_difference"],
        source_sha256_before=report["source_integrity"]["before"],
        source_sha256_after=report["source_integrity"]["after"],
        source_unchanged=report["source_integrity"]["unchanged"],
    )
