"""Core helpers for external-GCP image-to-map geometric correction.

The supported mathematical models are first/second/third-order polynomial and
thin-plate spline.  None of these models is a SAR sensor/orbit/DEM terrain
correction model.
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
from osgeo import gdal, osr

from .geometry_core import (
    GeometryCancelled,
    inspect_raster,
    sha256_file,
)
from .localization import tr


gdal.UseExceptions()

CancelCallback = Callable[[], bool] | None
ProgressCallback = Callable[[int, str], None] | None
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


def _check_cancelled(is_cancelled: CancelCallback) -> None:
    if is_cancelled is not None and is_cancelled():
        raise GeometryCancelled(_tr("用户取消了 GCP 几何校正任务。"))


def _progress(callback: ProgressCallback, value: int, message: str) -> None:
    if callback is not None:
        callback(max(0, min(100, int(value))), message)


@dataclass(frozen=True)
class RealControlPoint:
    point_id: str
    subset: str
    pixel: float
    line: float
    x: float
    y: float
    source_file: str
    source_row: int


POINT_FIELDS = [field.name for field in RealControlPoint.__dataclass_fields__.values()]

FIELD_ALIASES = {
    "point_id": ("point_id", "id", "name", "point", "点号"),
    "pixel": (
        "pixel",
        "sourcex",
        "source_x",
        "pixel_x",
        "column",
        "col",
        "像素",
        "列",
    ),
    "line": (
        "line",
        "sourcey",
        "source_y",
        "pixel_y",
        "row",
        "行",
    ),
    "x": ("x", "mapx", "map_x", "target_x", "地图x"),
    "y": ("y", "mapy", "map_y", "target_y", "地图y"),
    "enabled": ("enabled", "enable", "use", "active", "启用"),
}

MODEL_SPECS = {
    "affine": {
        "label": "一阶仿射",
        "minimum_train": 4,
        "gdal_polynomial_order": 1,
    },
    "polynomial2": {
        "label": "二阶多项式",
        "minimum_train": 8,
        "gdal_polynomial_order": 2,
    },
    "polynomial3": {
        "label": "三阶多项式",
        "minimum_train": 12,
        "gdal_polynomial_order": 3,
    },
    "tps": {
        "label": "薄板样条（TPS）",
        "minimum_train": 10,
        "gdal_polynomial_order": None,
    },
}


def localized_model_label(source_label: str) -> str:
    labels = {
        "一阶仿射": _tr("一阶仿射"),
        "二阶多项式": _tr("二阶多项式"),
        "三阶多项式": _tr("三阶多项式"),
        "薄板样条（TPS）": _tr("薄板样条（TPS）"),
    }
    return labels.get(source_label, source_label)


def _normalise_field(value: str) -> str:
    return value.strip().lower().replace(" ", "").replace("-", "_")


def _resolve_field(fieldnames: Sequence[str], logical_name: str) -> str | None:
    normalised = {_normalise_field(name): name for name in fieldnames}
    for alias in FIELD_ALIASES[logical_name]:
        candidate = normalised.get(_normalise_field(alias))
        if candidate is not None:
            return candidate
    return None


def _is_enabled(value: str | None) -> bool:
    if value is None or not value.strip():
        return True
    return value.strip().lower() not in {"0", "false", "no", "n", "否"}


def read_control_points(path: Path, subset: str) -> tuple[list[RealControlPoint], dict[str, Any]]:
    """Read standard CSV or QGIS Georeferencer .points control points.

    Standard CSV uses positive-down GDAL ``pixel``/``line`` coordinates.
    QGIS .points files commonly store ``sourceY`` as a negative value; when the
    sourceY header is present and every enabled sourceY is non-positive, this
    reader converts it to a positive-down GDAL line coordinate and records the
    conversion in the returned metadata.
    """

    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            _tr("控制点文件不存在：{path}").format(path=path)
        )
    if subset not in {"train", "check"}:
        raise ValueError(
            _tr("未知控制点子集：{subset}").format(subset=subset)
        )

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError(
                _tr("控制点文件缺少表头：{path}").format(path=path)
            )
        fields = {
            name: _resolve_field(reader.fieldnames, name)
            for name in ("point_id", "pixel", "line", "x", "y", "enabled")
        }
        missing = [name for name in ("pixel", "line", "x", "y") if not fields[name]]
        if missing:
            raise ValueError(
                _tr(
                    "控制点文件缺少必要字段{missing}：{filename}；"
                    "需要pixel,line,x,y，或QGIS的sourceX,sourceY,mapX,mapY。"
                ).format(missing=missing, filename=path.name)
            )
        rows = [row for row in reader if _is_enabled(row.get(fields["enabled"]))]  # type: ignore[arg-type]

    if not rows:
        raise ValueError(
            _tr("控制点文件没有启用的点：{path}").format(path=path)
        )

    line_field = str(fields["line"])
    qgis_source_y = _normalise_field(line_field) in {"sourcey", "source_y"}
    raw_lines = [float(row[line_field]) for row in rows]
    invert_source_y = qgis_source_y and all(value <= 0.0 for value in raw_lines)

    points: list[RealControlPoint] = []
    for row_number, row in enumerate(rows, start=2):
        try:
            pixel = float(row[str(fields["pixel"])])
            line = float(row[line_field])
            x = float(row[str(fields["x"])])
            y = float(row[str(fields["y"])])
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError(
                _tr("{filename}第{row}行含非数值控制点坐标。").format(
                    filename=path.name,
                    row=row_number,
                )
            ) from exc
        if invert_source_y:
            line = -line
        values = (pixel, line, x, y)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(
                _tr("{filename}第{row}行含非有限数值。").format(
                    filename=path.name,
                    row=row_number,
                )
            )
        identifier_field = fields["point_id"]
        identifier = (
            str(row.get(identifier_field, "")).strip()
            if identifier_field is not None
            else ""
        )
        points.append(
            RealControlPoint(
                point_id=identifier or f"{subset.upper()}_{len(points) + 1:03d}",
                subset=subset,
                pixel=pixel,
                line=line,
                x=x,
                y=y,
                source_file=str(path),
                source_row=row_number,
            )
        )
    return points, {
        "path": str(path),
        "sha256": sha256_file(path),
        "enabled_point_count": len(points),
        "line_coordinate_conversion": (
            "QGIS sourceY values inverted to GDAL positive-down line"
            if invert_source_y
            else "no conversion; positive-down GDAL line expected"
        ),
        "fields": fields,
    }


def write_control_points(path: Path, points: Iterable[RealControlPoint]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=POINT_FIELDS)
        writer.writeheader()
        for point in points:
            writer.writerow(asdict(point))


def spatial_reference(value: str) -> osr.SpatialReference:
    srs = osr.SpatialReference()
    if srs.SetFromUserInput(value.strip()) != 0:
        raise ValueError(
            _tr("无法识别目标坐标系：{value}").format(value=value)
        )
    if hasattr(srs, "SetAxisMappingStrategy"):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs


def validate_real_control_points(
    train: Sequence[RealControlPoint],
    check: Sequence[RealControlPoint],
    width: int,
    height: int,
    model: str = "affine",
) -> dict[str, Any]:
    problems: list[str] = []
    warnings: list[str] = []
    spec = MODEL_SPECS.get(model)
    if spec is None:
        problems.append(
            _tr("不支持的几何变换模型：{model}").format(model=model)
        )
        spec = MODEL_SPECS["affine"]
    minimum_train = int(spec["minimum_train"])
    if len(train) < minimum_train:
        problems.append(
            _tr(
                "{model_label}至少需要{minimum}个启用的训练GCP，"
                "其中包含用于稳定性检查的冗余点。"
            ).format(
                model_label=localized_model_label(str(spec["label"])),
                minimum=minimum_train,
            )
        )
    if len(check) < 3:
        problems.append(_tr("独立精度检查至少需要3个检查点。"))

    combined = list(train) + list(check)
    ids = [point.point_id for point in combined]
    if len(ids) != len(set(ids)):
        problems.append(_tr("训练点与检查点的point_id必须全局唯一。"))
    pixel_locations = [(round(p.pixel, 9), round(p.line, 9)) for p in combined]
    if len(pixel_locations) != len(set(pixel_locations)):
        problems.append(_tr("训练点和检查点不能使用相同的影像像素位置。"))

    for point in combined:
        if not (-0.5 <= point.pixel <= width - 0.5):
            problems.append(
                _tr(
                    "{point_id}的pixel={pixel}超出影像宽度0…{maximum}。"
                ).format(
                    point_id=point.point_id,
                    pixel=point.pixel,
                    maximum=width - 1,
                )
            )
        if not (-0.5 <= point.line <= height - 0.5):
            problems.append(
                _tr(
                    "{point_id}的line={line}超出影像高度0…{maximum}。"
                ).format(
                    point_id=point.point_id,
                    line=point.line,
                    maximum=height - 1,
                )
            )

    fit: dict[str, Any] | None = None
    if len(train) >= minimum_train:
        try:
            fit = fit_transform_model(train, model)
            if float(fit["normalised_condition_number"]) > 1.0e6:
                warnings.append(
                    _tr("训练GCP空间分布较差，模型解算条件数偏大。")
                )
        except ValueError as exc:
            problems.append(str(exc))

    train_x = [point.pixel for point in train]
    train_y = [point.line for point in train]
    if train_x and train_y:
        coverage_x = (max(train_x) - min(train_x)) / max(1.0, width - 1)
        coverage_y = (max(train_y) - min(train_y)) / max(1.0, height - 1)
        if coverage_x < 0.5 or coverage_y < 0.5:
            warnings.append(
                _tr(
                    "训练GCP未覆盖影像至少50%的宽度或高度，外推区域可能不稳定。"
                )
            )
    else:
        coverage_x = coverage_y = 0.0

    return {
        "errors": problems,
        "warnings": warnings,
        "fit": fit,
        "coverage_x_ratio": coverage_x,
        "coverage_y_ratio": coverage_y,
    }


def fit_affine(points: Sequence[RealControlPoint]) -> dict[str, Any]:
    if len(points) < 3:
        raise ValueError(_tr("仿射模型至少需要3个训练GCP。"))
    pixels = np.asarray([[p.pixel, p.line] for p in points], dtype=np.float64)
    centre = pixels.mean(axis=0)
    scale = pixels.std(axis=0)
    if np.any(scale <= 1.0e-12):
        raise ValueError(
            _tr("训练GCP在行或列方向没有足够分布，无法拟合仿射模型。")
        )
    normalised = (pixels - centre) / scale
    design_n = np.column_stack([np.ones(len(points)), normalised])
    rank = int(np.linalg.matrix_rank(design_n))
    if rank != 3:
        raise ValueError(
            _tr("训练GCP共线或分布退化，仿射设计矩阵秩不足。")
        )

    design = np.column_stack([np.ones(len(points)), pixels])
    targets = np.asarray([[p.x, p.y] for p in points], dtype=np.float64)
    coefficients, _, raw_rank, singular_values = np.linalg.lstsq(
        design, targets, rcond=None
    )
    if int(raw_rank) != 3:
        raise ValueError(_tr("训练GCP仿射解算失败。"))
    return {
        "model": "affine",
        "label": MODEL_SPECS["affine"]["label"],
        "coefficients": coefficients,
        "rank": int(raw_rank),
        "singular_values": singular_values.tolist(),
        "normalised_condition_number": float(np.linalg.cond(design_n)),
        "geotransform": [
            float(coefficients[0, 0]),
            float(coefficients[1, 0]),
            float(coefficients[2, 0]),
            float(coefficients[0, 1]),
            float(coefficients[1, 1]),
            float(coefficients[2, 1]),
        ],
    }


def _polynomial_terms(x: np.ndarray, y: np.ndarray, order: int) -> np.ndarray:
    """Return terms in GDAL-compatible total-degree order."""

    columns: list[np.ndarray] = []
    for degree in range(order + 1):
        for y_power in range(degree + 1):
            x_power = degree - y_power
            columns.append((x**x_power) * (y**y_power))
    return np.column_stack(columns)


def _fit_polynomial(
    points: Sequence[RealControlPoint],
    order: int,
) -> dict[str, Any]:
    model = f"polynomial{order}"
    minimum = int(MODEL_SPECS[model]["minimum_train"])
    if len(points) < minimum:
        raise ValueError(
            _tr("{model_label}至少需要{minimum}个训练GCP。").format(
                model_label=localized_model_label(
                    str(MODEL_SPECS[model]["label"])
                ),
                minimum=minimum,
            )
        )
    pixels = np.asarray([[p.pixel, p.line] for p in points], dtype=np.float64)
    centre = pixels.mean(axis=0)
    scale = pixels.std(axis=0)
    if np.any(scale <= 1.0e-12):
        raise ValueError(_tr("训练GCP在行或列方向没有足够分布。"))
    normalised = (pixels - centre) / scale
    design = _polynomial_terms(normalised[:, 0], normalised[:, 1], order)
    expected_rank = design.shape[1]
    rank = int(np.linalg.matrix_rank(design))
    if rank != expected_rank:
        raise ValueError(
            _tr(
                "{model_label}设计矩阵秩不足；"
                "请增加分布均匀且不共线的训练GCP。"
            ).format(
                model_label=localized_model_label(
                    str(MODEL_SPECS[model]["label"])
                )
            )
        )
    targets = np.asarray([[p.x, p.y] for p in points], dtype=np.float64)
    coefficients, _, _, singular_values = np.linalg.lstsq(
        design, targets, rcond=None
    )
    return {
        "model": model,
        "label": MODEL_SPECS[model]["label"],
        "order": order,
        "coefficients": coefficients,
        "pixel_centre": centre,
        "pixel_scale": scale,
        "rank": rank,
        "singular_values": singular_values.tolist(),
        "normalised_condition_number": float(np.linalg.cond(design)),
    }


def _tps_kernel(radius_squared: np.ndarray) -> np.ndarray:
    safe = np.where(radius_squared > 0.0, radius_squared, 1.0)
    return np.where(radius_squared > 0.0, radius_squared * np.log(safe), 0.0)


def _fit_tps(points: Sequence[RealControlPoint]) -> dict[str, Any]:
    minimum = int(MODEL_SPECS["tps"]["minimum_train"])
    if len(points) < minimum:
        raise ValueError(
            _tr("薄板样条（TPS）至少需要{minimum}个训练GCP。").format(
                minimum=minimum
            )
        )
    pixels = np.asarray([[p.pixel, p.line] for p in points], dtype=np.float64)
    centre = pixels.mean(axis=0)
    scale = pixels.std(axis=0)
    if np.any(scale <= 1.0e-12):
        raise ValueError(_tr("训练GCP在行或列方向没有足够分布。"))
    control = (pixels - centre) / scale
    delta = control[:, None, :] - control[None, :, :]
    kernel = _tps_kernel(np.sum(delta * delta, axis=2))
    affine = np.column_stack([np.ones(len(points)), control])
    system = np.block(
        [
            [kernel, affine],
            [affine.T, np.zeros((3, 3), dtype=np.float64)],
        ]
    )
    rank = int(np.linalg.matrix_rank(system))
    if rank != system.shape[0]:
        raise ValueError(
            _tr("TPS控制点分布退化；请增加分布均匀且不重合的训练GCP。")
        )
    targets = np.asarray([[p.x, p.y] for p in points], dtype=np.float64)
    right = np.vstack([targets, np.zeros((3, 2), dtype=np.float64)])
    solution = np.linalg.solve(system, right)
    return {
        "model": "tps",
        "label": MODEL_SPECS["tps"]["label"],
        "coefficients": solution,
        "control_pixels": control,
        "pixel_centre": centre,
        "pixel_scale": scale,
        "rank": rank,
        "singular_values": np.linalg.svd(system, compute_uv=False).tolist(),
        "normalised_condition_number": float(np.linalg.cond(system)),
    }


def fit_transform_model(
    points: Sequence[RealControlPoint],
    model: str,
) -> dict[str, Any]:
    if model == "affine":
        return fit_affine(points)
    if model == "polynomial2":
        return _fit_polynomial(points, 2)
    if model == "polynomial3":
        return _fit_polynomial(points, 3)
    if model == "tps":
        return _fit_tps(points)
    raise ValueError(
        _tr("不支持的几何变换模型：{model}").format(model=model)
    )


def predict_map_coordinates(
    point: RealControlPoint,
    fit: dict[str, Any],
) -> np.ndarray:
    model = str(fit.get("model", "affine"))
    coefficients = np.asarray(fit["coefficients"], dtype=np.float64)
    if model == "affine":
        return np.asarray([1.0, point.pixel, point.line]) @ coefficients
    centre = np.asarray(fit["pixel_centre"], dtype=np.float64)
    scale = np.asarray(fit["pixel_scale"], dtype=np.float64)
    location = (np.asarray([point.pixel, point.line]) - centre) / scale
    if model.startswith("polynomial"):
        terms = _polynomial_terms(
            np.asarray([location[0]]),
            np.asarray([location[1]]),
            int(fit["order"]),
        )
        return terms[0] @ coefficients
    if model == "tps":
        control = np.asarray(fit["control_pixels"], dtype=np.float64)
        delta = control - location
        radial = _tps_kernel(np.sum(delta * delta, axis=1))
        vector = np.concatenate([radial, [1.0, location[0], location[1]]])
        return vector @ coefficients
    raise ValueError(
        _tr("无法预测未知模型：{model}").format(model=model)
    )


def _metric_transform(target_srs: osr.SpatialReference, points: Sequence[RealControlPoint]):
    if target_srs.IsProjected():
        return None, float(target_srs.GetLinearUnits() or 1.0), target_srs.GetLinearUnitsName()
    if not target_srs.IsGeographic():
        return None, None, "unknown"
    lon = float(np.mean([p.x for p in points]))
    lat = float(np.mean([p.y for p in points]))
    zone = max(1, min(60, int((lon + 180.0) // 6.0) + 1))
    epsg = (32600 if lat >= 0 else 32700) + zone
    metric = osr.SpatialReference()
    metric.ImportFromEPSG(epsg)
    if hasattr(metric, "SetAxisMappingStrategy"):
        metric.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(target_srs, metric), 1.0, f"EPSG:{epsg}"


def calculate_residuals(
    points: Sequence[RealControlPoint],
    coefficients: np.ndarray | dict[str, Any],
    target_srs: osr.SpatialReference,
    output_geotransform: Sequence[float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not points:
        raise ValueError(_tr("残差计算没有控制点。"))
    metric_transform, linear_to_metre, metric_name = _metric_transform(
        target_srs, points
    )
    pixel_matrix = np.asarray(
        [
            [output_geotransform[1], output_geotransform[2]],
            [output_geotransform[4], output_geotransform[5]],
        ],
        dtype=np.float64,
    )
    rows: list[dict[str, Any]] = []
    for point in points:
        predicted = (
            predict_map_coordinates(point, coefficients)
            if isinstance(coefficients, dict)
            else np.asarray([1.0, point.pixel, point.line]) @ coefficients
        )
        predicted_x = float(predicted[0])
        predicted_y = float(predicted[1])
        dx = predicted_x - point.x
        dy = predicted_y - point.y
        if metric_transform is not None:
            expected_m = metric_transform.TransformPoint(point.x, point.y)
            predicted_m = metric_transform.TransformPoint(predicted_x, predicted_y)
            dx_m = float(predicted_m[0] - expected_m[0])
            dy_m = float(predicted_m[1] - expected_m[1])
        elif linear_to_metre is not None:
            dx_m = dx * linear_to_metre
            dy_m = dy * linear_to_metre
        else:
            dx_m = dy_m = float("nan")
        error_m = math.hypot(dx_m, dy_m)
        pixel_delta = np.linalg.solve(pixel_matrix, np.asarray([dx, dy]))
        error_pixel = float(math.hypot(pixel_delta[0], pixel_delta[1]))
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
                "dx_map_unit": dx,
                "dy_map_unit": dy,
                "error_map_unit": math.hypot(dx, dy),
                "dx_m": dx_m,
                "dy_m": dy_m,
                "error_m": error_m,
                "d_pixel": float(pixel_delta[0]),
                "d_line": float(pixel_delta[1]),
                "error_pixel": error_pixel,
            }
        )

    def rmse(name: str) -> float:
        return float(math.sqrt(np.mean([float(row[name]) ** 2 for row in rows])))

    metrics = {
        "point_count": len(rows),
        "metric_reference": metric_name,
        "rmse_x_map_unit": rmse("dx_map_unit"),
        "rmse_y_map_unit": rmse("dy_map_unit"),
        "rmse_2d_map_unit": float(
            math.sqrt(np.mean([float(row["error_map_unit"]) ** 2 for row in rows]))
        ),
        "rmse_x_m": rmse("dx_m"),
        "rmse_y_m": rmse("dy_m"),
        "rmse_2d_m": float(
            math.sqrt(np.mean([float(row["error_m"]) ** 2 for row in rows]))
        ),
        "max_error_m": float(max(row["error_m"] for row in rows)),
        "rmse_pixel": float(
            math.sqrt(np.mean([float(row["error_pixel"]) ** 2 for row in rows]))
        ),
        "max_error_pixel": float(max(row["error_pixel"] for row in rows)),
    }
    return rows, metrics


def write_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(
            _tr("没有可写入的残差记录：{path}").format(path=path)
        )
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _quicklook(path: Path, max_size: int = 1200) -> np.ndarray:
    dataset = gdal.OpenEx(str(path), gdal.OF_RASTER | gdal.OF_READONLY)
    if dataset is None or dataset.RasterCount < 1:
        raise RuntimeError(
            _tr("无法读取预览栅格：{path}").format(path=path)
        )
    scale = min(1.0, max_size / max(dataset.RasterXSize, dataset.RasterYSize))
    width = max(1, int(round(dataset.RasterXSize * scale)))
    height = max(1, int(round(dataset.RasterYSize * scale)))
    band = dataset.GetRasterBand(1)
    array = band.ReadAsArray(buf_xsize=width, buf_ysize=height).astype(np.float32)
    nodata = band.GetNoDataValue()
    valid = np.isfinite(array)
    if nodata is not None:
        valid &= array != nodata
    if not np.any(valid):
        result = np.zeros((height, width), dtype=np.uint8)
    else:
        low, high = np.percentile(array[valid], [2.0, 98.0])
        if (
            not math.isfinite(float(low))
            or not math.isfinite(float(high))
            or high <= low
        ):
            low = float(np.min(array[valid]))
            high = float(np.max(array[valid]))
        if high <= low:
            high = low + 1.0
        normalised = np.clip((array - low) / (high - low), 0.0, 1.0)
        result = np.where(valid, normalised * 255.0, 0.0).astype(np.uint8)
    dataset = None
    return result


def render_real_geometry_preview(
    source_path: Path,
    output_path: Path,
    train: Sequence[RealControlPoint],
    check: Sequence[RealControlPoint],
    train_rows: Sequence[dict[str, Any]],
    check_rows: Sequence[dict[str, Any]],
    output_png: Path,
    model_label: str = "一阶仿射",
) -> None:
    """Render a compact GCP distribution and residual QA figure."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    source_info = inspect_raster(source_path)
    source = _quicklook(source_path)
    corrected = _quicklook(output_path)
    x_scale = source.shape[1] / float(source_info["width"])
    y_scale = source.shape[0] / float(source_info["height"])

    figure, axes = plt.subplots(2, 2, figsize=(14, 11), constrained_layout=True)
    axes[0, 0].imshow(source, cmap="gray", vmin=0, vmax=255)
    axes[0, 0].scatter(
        [point.pixel * x_scale for point in train],
        [point.line * y_scale for point in train],
        s=34,
        facecolors="none",
        edgecolors="#00ffff",
        linewidths=1.2,
        label=_tr("训练 GCP（{count}）").format(count=len(train)),
    )
    axes[0, 0].scatter(
        [point.pixel * x_scale for point in check],
        [point.line * y_scale for point in check],
        s=38,
        marker="x",
        c="#ffcc00",
        linewidths=1.4,
        label=_tr("独立检查点（{count}）").format(count=len(check)),
    )
    axes[0, 0].set_title(_tr("输入栅格与控制点分布"))
    axes[0, 0].legend(loc="best", fontsize=9)
    axes[0, 0].axis("off")

    axes[0, 1].imshow(corrected, cmap="gray", vmin=0, vmax=255)
    axes[0, 1].set_title(_tr("校正 GeoTIFF 快视图"))
    axes[0, 1].axis("off")

    train_errors = [float(row["error_pixel"]) for row in train_rows]
    check_errors = [float(row["error_pixel"]) for row in check_rows]
    axes[1, 0].bar(
        np.arange(len(train_errors)),
        train_errors,
        color="#3b82f6",
        alpha=0.75,
        label=_tr("训练点"),
    )
    offset = len(train_errors) + 1
    axes[1, 0].bar(
        offset + np.arange(len(check_errors)),
        check_errors,
        color="#f59e0b",
        alpha=0.8,
        label=_tr("独立检查点"),
    )
    axes[1, 0].set_title(_tr("控制点残差大小"))
    axes[1, 0].set_xlabel(_tr("点序号"))
    axes[1, 0].set_ylabel(_tr("误差（输出像素）"))
    axes[1, 0].grid(axis="y", alpha=0.25)
    axes[1, 0].legend()

    train_rmse = math.sqrt(np.mean(np.square(train_errors)))
    check_rmse = math.sqrt(np.mean(np.square(check_errors)))
    max_check = max(check_errors)
    axes[1, 1].axis("off")
    axes[1, 1].text(
        0.04,
        0.94,
        _tr(
            "真实几何校正质量检查\n\n"
            "模型：{model_label}\n"
            "训练 GCP：{train_count}\n"
            "独立检查点：{check_count}\n"
            "训练 RMSE：{train_rmse:.6f} 像素\n"
            "检查 RMSE：{check_rmse:.6f} 像素\n"
            "检查最大误差：{max_check:.6f} 像素\n\n"
            "只有当检查点独立于训练 GCP，且两者均来自\n"
            "可靠外部参考时，精度评价才有效。\n\n"
            "本流程不是 SAR 轨道/DEM 地形校正。"
        ).format(
            model_label=localized_model_label(model_label),
            train_count=len(train),
            check_count=len(check),
            train_rmse=train_rmse,
            check_rmse=check_rmse,
            max_check=max_check,
        ),
        va="top",
        ha="left",
        fontsize=12,
        family="DejaVu Sans",
    )
    figure.suptitle(
        _tr("外部 GCP 几何校正与独立精度检查"),
        fontsize=16,
        weight="bold",
    )
    figure.savefig(output_png, dpi=150, facecolor="white")
    plt.close(figure)


def georeference_with_external_gcps(
    source_path: Path,
    output_path: Path,
    train: Sequence[RealControlPoint],
    target_srs_text: str,
    *,
    resampling: str,
    x_resolution: float,
    y_resolution: float,
    run_id: str,
    transform_model: str = "affine",
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    _check_cancelled(is_cancelled)
    if output_path.exists():
        raise FileExistsError(
            _tr("输出已存在：{path}").format(path=output_path)
        )
    partial = output_path.with_name(f".{output_path.stem}.partial.tif")
    if partial.exists():
        raise FileExistsError(
            _tr("临时输出已存在：{path}").format(path=partial)
        )

    source_info = inspect_raster(source_path)
    target_srs = spatial_reference(target_srs_text)
    gcps = [gdal.GCP(p.x, p.y, 0.0, p.pixel, p.line) for p in train]
    vrt_path = f"/vsimem/real-geometry-{os.getpid()}-{run_id}.vrt"
    translated = gdal.Translate(
        vrt_path,
        str(source_path),
        options=gdal.TranslateOptions(
            format="VRT",
            GCPs=gcps,
            outputSRS=target_srs.ExportToWkt(),
        ),
    )
    if translated is None:
        raise RuntimeError(_tr("无法将外部训练GCP附加到输入影像。"))
    translated.FlushCache()
    translated = None

    def warp_progress(fraction, message, _data):
        _progress(
            progress,
            int(float(fraction) * 100),
            message or _tr("正在执行外部GCP几何校正Warp……"),
        )
        return 0 if is_cancelled is not None and is_cancelled() else 1

    options: dict[str, Any] = {
        "format": "GTiff",
        "dstSRS": target_srs.ExportToWkt(),
        "errorThreshold": 0.0,
        "resampleAlg": resampling,
        "multithread": True,
        "callback": warp_progress,
        "creationOptions": [
            "COMPRESS=LZW",
            "TILED=YES",
            "BIGTIFF=IF_SAFER",
        ],
    }
    if transform_model == "tps":
        options["tps"] = True
    else:
        spec = MODEL_SPECS.get(transform_model)
        if spec is None or spec["gdal_polynomial_order"] is None:
            raise ValueError(
                _tr("不支持的几何变换模型：{model}").format(
                    model=transform_model
                )
            )
        options["polynomialOrder"] = int(spec["gdal_polynomial_order"])
    if x_resolution > 0.0 and y_resolution > 0.0:
        options.update(
            {
                "xRes": x_resolution,
                "yRes": y_resolution,
                "targetAlignedPixels": True,
            }
        )
    if source_info["nodata"] is not None:
        options["srcNodata"] = source_info["nodata"]
        options["dstNodata"] = source_info["nodata"]

    try:
        try:
            warped = gdal.Warp(
                str(partial),
                vrt_path,
                options=gdal.WarpOptions(**options),
            )
        except RuntimeError as exc:
            if is_cancelled is not None and is_cancelled():
                raise GeometryCancelled(
                    _tr("用户在真实GCP Warp过程中取消了任务。")
                ) from exc
            raise
    finally:
        gdal.Unlink(vrt_path)
    _check_cancelled(is_cancelled)
    if warped is None:
        raise RuntimeError(_tr("GDAL外部GCP几何校正Warp失败。"))
    warped.SetMetadataItem("PURPOSE", "real_image_to_map_geometric_correction")
    warped.SetMetadataItem(
        "METHOD",
        f"external training GCPs; {MODEL_SPECS[transform_model]['label']}",
    )
    warped.SetMetadataItem("TRANSFORM_MODEL", transform_model)
    warped.SetMetadataItem("RUN_ID", run_id)
    warped.SetMetadataItem("SOURCE_SHA256", source_info["sha256"])
    warped.SetMetadataItem("TRAINING_POINT_COUNT", str(len(train)))
    warped.SetMetadataItem("RESAMPLING", resampling)
    warped.FlushCache()
    warped = None
    partial.replace(output_path)
    result = inspect_raster(output_path)
    if not result["projection_wkt"] or result["geotransform"] is None:
        raise RuntimeError(_tr("校正成果缺少坐标系或GeoTransform。"))
    return result
