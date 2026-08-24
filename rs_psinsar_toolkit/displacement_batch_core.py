"""Streaming/memory-mapped core for 50 m cumulative-displacement grids."""

from __future__ import annotations

import hashlib
import gc
import json
import math
import os
import shutil
import sqlite3
import struct
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
from osgeo import ogr, osr
from pyproj import Transformer

from .localization import tr
from .displacement_batch_settings import (
    BATCH_ENGINE_VERSION,
    DEFAULT_GRID_SIZE_M,
    FULL_LAYER_NAME,
    BatchMapSettings,
    TimeField,
    read_time_catalog,
)


ogr.UseExceptions()

ProgressCallback = Callable[[int, str], None]
CancelCallback = Callable[[], bool]
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


class BatchCancelled(RuntimeError):
    """Raised after a cooperative cancellation request."""


class BatchCoreError(RuntimeError):
    """Raised when a scientific or persistence quality gate fails."""


@dataclass(frozen=True)
class PeriodGridSummary:
    source_field: str
    output_field: str
    acquisition_date: str
    valid_point_count: int
    invalid_point_count: int
    full_minimum_m: float
    full_maximum_m: float
    grid_median_minimum_m: float
    grid_median_maximum_m: float


@dataclass(frozen=True)
class GridBuildResult:
    output_gpkg: Path
    feature_count: int
    occupied_cell_count: int
    origin_x: float
    origin_y: float
    width: int
    height: int
    grid_size_m: float
    initial_field: str
    initial_date: str
    periods: tuple[PeriodGridSummary, ...]
    input_sha256: str
    output_sha256: str
    validation: dict[str, bool]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(
    path: Path,
    block_size: int = 16 * 1024 * 1024,
) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest().upper()


def _write_json(path: Path, value: Any, *, exclusive: bool = True) -> None:
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _check_cancelled(is_cancelled: CancelCallback) -> None:
    if is_cancelled():
        raise BatchCancelled(_tr("用户取消了累计形变批量任务。"))


def _emit(
    progress: ProgressCallback,
    value: int,
    message: str,
) -> None:
    progress(max(0, min(100, int(value))), message)


def parse_gpkg_point_xy(blob: bytes) -> tuple[float, float]:
    """Return exact X/Y from a GeoPackage POINT/POINT Z geometry blob."""
    if len(blob) < 29 or blob[:2] != b"GP":
        raise ValueError(_tr("无效的GeoPackage点几何。"))
    flags = blob[3]
    envelope_code = (flags >> 1) & 0x07
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    if envelope_code not in envelope_sizes:
        raise ValueError(
            _tr("不支持的GeoPackage包络代码：{code}").format(code=envelope_code)
        )
    wkb_offset = 8 + envelope_sizes[envelope_code]
    byte_order = blob[wkb_offset]
    if byte_order == 1:
        endian = "<"
    elif byte_order == 0:
        endian = ">"
    else:
        raise ValueError(_tr("无效的WKB字节序。"))
    geometry_type = struct.unpack_from(endian + "I", blob, wkb_offset + 1)[0]
    if geometry_type % 1000 != 1:
        raise ValueError(
            _tr("需要POINT几何，实际WKB类型为{geometry_type}。").format(
                geometry_type=geometry_type
            )
        )
    return struct.unpack_from(endian + "dd", blob, wkb_offset + 5)


def _catalog_for_selection(
    gpkg: Path,
    selected_fields: tuple[str, ...],
) -> tuple[TimeField, tuple[TimeField, ...]]:
    catalog = read_time_catalog(gpkg)
    initial = [item for item in catalog if item.is_initial]
    if len(initial) != 1:
        raise BatchCoreError(_tr("time_catalog必须且只能标记一个初始时相。"))
    lookup = {item.field_name: item for item in catalog}
    missing = sorted(set(selected_fields) - set(lookup))
    if missing:
        raise BatchCoreError(
            _tr("时相字段缺失：{fields}").format(fields=", ".join(missing))
        )
    selected = tuple(lookup[name] for name in selected_fields)
    return initial[0], selected


def _create_field(
    layer: ogr.Layer,
    name: str,
    field_type: int,
    width: int | None = None,
) -> None:
    definition = ogr.FieldDefn(name, field_type)
    if width is not None:
        definition.SetWidth(width)
    if layer.CreateField(definition) != ogr.OGRERR_NONE:
        raise BatchCoreError(_tr("无法创建字段：{name}").format(name=name))


def _spatial_reference(epsg: int) -> osr.SpatialReference:
    reference = osr.SpatialReference()
    reference.ImportFromEPSG(epsg)
    if hasattr(reference, "SetAxisMappingStrategy"):
        reference.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return reference


def _polygon_for_cell(
    origin_x: float,
    origin_y: float,
    row: int,
    column: int,
    size: float,
) -> ogr.Geometry:
    x0 = origin_x + column * size
    y0 = origin_y + row * size
    x1 = x0 + size
    y1 = y0 + size
    ring = ogr.Geometry(ogr.wkbLinearRing)
    ring.AddPoint_2D(x0, y0)
    ring.AddPoint_2D(x1, y0)
    ring.AddPoint_2D(x1, y1)
    ring.AddPoint_2D(x0, y1)
    ring.AddPoint_2D(x0, y0)
    polygon = ogr.Geometry(ogr.wkbPolygon)
    polygon.AddGeometry(ring)
    return polygon


def _write_grid_geopackage(
    building_path: Path,
    final_path: Path,
    *,
    unique_dense: np.ndarray,
    counts: np.ndarray,
    medians: np.ndarray,
    period_summaries: list[PeriodGridSummary],
    initial: TimeField,
    origin_x: float,
    origin_y: float,
    width: int,
    height: int,
    grid_size_m: float,
    progress: ProgressCallback,
    is_cancelled: CancelCallback,
) -> None:
    driver = ogr.GetDriverByName("GPKG")
    dataset = driver.CreateDataSource(str(building_path))
    if dataset is None:
        raise BatchCoreError(
            _tr("无法创建派生GeoPackage：{path}").format(path=building_path)
        )
    grid_layer = dataset.CreateLayer(
        "cumulative_displacement_grid_50m",
        srs=_spatial_reference(32650),
        geom_type=ogr.wkbPolygon,
        options=["SPATIAL_INDEX=YES"],
    )
    for name, field_type, width_value in (
        ("cell_id", ogr.OFTInteger64, None),
        ("grid_row", ogr.OFTInteger, None),
        ("grid_col", ogr.OFTInteger, None),
        ("point_n", ogr.OFTInteger, None),
    ):
        _create_field(grid_layer, name, field_type, width_value)
    for summary in period_summaries:
        _create_field(grid_layer, summary.output_field, ogr.OFTReal)

    definition = grid_layer.GetLayerDefn()
    grid_layer.StartTransaction()
    total = int(unique_dense.size)
    for index, dense_value in enumerate(unique_dense):
        if index % 500 == 0:
            _check_cancelled(is_cancelled)
            _emit(
                progress,
                78 + int(10 * index / max(1, total)),
                _tr("写入50米累计形变网格：{index:,}/{total:,}").format(
                    index=index, total=total
                ),
            )
        dense = int(dense_value)
        row = dense // width
        column = dense % width
        feature = ogr.Feature(definition)
        feature.SetGeometry(
            _polygon_for_cell(
                origin_x,
                origin_y,
                row,
                column,
                grid_size_m,
            )
        )
        feature.SetField("cell_id", dense)
        feature.SetField("grid_row", row)
        feature.SetField("grid_col", column)
        feature.SetField("point_n", int(counts[index]))
        for period_index, summary in enumerate(period_summaries):
            value = float(medians[index, period_index])
            if math.isfinite(value):
                feature.SetField(summary.output_field, value)
        if grid_layer.CreateFeature(feature) != ogr.OGRERR_NONE:
            raise BatchCoreError(_tr("无法写入网格：{value}").format(value=dense))
        if (index + 1) % 5_000 == 0:
            grid_layer.CommitTransaction()
            grid_layer.StartTransaction()
    grid_layer.CommitTransaction()

    period_layer = dataset.CreateLayer(
        "period_catalog",
        srs=None,
        geom_type=ogr.wkbNone,
    )
    for name, field_type, width_value in (
        ("ordinal", ogr.OFTInteger, None),
        ("source_field", ogr.OFTString, 32),
        ("output_field", ogr.OFTString, 32),
        ("date", ogr.OFTString, 10),
        ("initial_field", ogr.OFTString, 32),
        ("initial_date", ogr.OFTString, 10),
        ("formula", ogr.OFTString, 80),
        ("unit", ogr.OFTString, 8),
    ):
        _create_field(period_layer, name, field_type, width_value)
    period_definition = period_layer.GetLayerDefn()
    for index, summary in enumerate(period_summaries, start=1):
        feature = ogr.Feature(period_definition)
        feature.SetField("ordinal", index)
        feature.SetField("source_field", summary.source_field)
        feature.SetField("output_field", summary.output_field)
        feature.SetField("date", summary.acquisition_date)
        feature.SetField("initial_field", initial.field_name)
        feature.SetField("initial_date", initial.acquisition_date)
        feature.SetField("formula", "D_target - D_initial")
        feature.SetField("unit", "mm")
        period_layer.CreateFeature(feature)

    metadata_layer = dataset.CreateLayer(
        "processing_metadata",
        srs=None,
        geom_type=ogr.wkbNone,
    )
    _create_field(metadata_layer, "key", ogr.OFTString, 80)
    _create_field(metadata_layer, "value", ogr.OFTString, 254)
    metadata_definition = metadata_layer.GetLayerDefn()
    metadata = {
        "batch_engine_version": BATCH_ENGINE_VERSION,
        "created_utc": _utc_now(),
        "formula": "delta_mm = D_target - D_initial",
        "initial_field": initial.field_name,
        "initial_date": initial.acquisition_date,
        "unit": "mm",
        "positive_direction": "vertical upward",
        "negative_direction": "vertical downward",
        "grid_size_m": str(grid_size_m),
        "occupied_cell_count": str(total),
        "extreme_point_layer_included": "false",
        "aggregation": "median of valid pointwise deltas per 50 m cell",
    }
    for key, value in metadata.items():
        feature = ogr.Feature(metadata_definition)
        feature.SetField("key", key)
        feature.SetField("value", value)
        metadata_layer.CreateFeature(feature)

    dataset = None
    if final_path.exists():
        raise FileExistsError(final_path)
    os.replace(building_path, final_path)


def _validate_grid_gpkg(
    path: Path,
    expected_cells: int,
    period_summaries: list[PeriodGridSummary],
) -> dict[str, bool]:
    connection = sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro",
        uri=True,
    )
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM gpkg_contents"
            ).fetchall()
        }
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(cumulative_displacement_grid_50m)"
            ).fetchall()
        }
        output_fields = {item.output_field for item in period_summaries}
        return {
            "grid_layer_present": (
                "cumulative_displacement_grid_50m" in tables
            ),
            "period_catalog_present": "period_catalog" in tables,
            "processing_metadata_present": "processing_metadata" in tables,
            "grid_feature_count": int(
                connection.execute(
                    "SELECT COUNT(*) "
                    "FROM cumulative_displacement_grid_50m"
                ).fetchone()[0]
            )
            == expected_cells,
            "all_period_fields_present": output_fields <= columns,
            "period_catalog_count": int(
                connection.execute(
                    "SELECT COUNT(*) FROM period_catalog"
                ).fetchone()[0]
            )
            == len(period_summaries),
            "spatial_index_present": int(
                connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type='table' AND "
                    "name='rtree_cumulative_displacement_grid_50m_geom'"
                ).fetchone()[0]
            )
            == 1,
        }
    finally:
        connection.close()


def build_cumulative_grid(
    settings: BatchMapSettings,
    run_dir: str | Path,
    *,
    progress: ProgressCallback | None = None,
    is_cancelled: CancelCallback | None = None,
    fetch_size: int = 10_000,
) -> GridBuildResult:
    """Build one wide 50 m grid layer for all selected target periods."""
    progress = progress or (lambda _value, _message: None)
    is_cancelled = is_cancelled or (lambda: False)
    run_dir = Path(run_dir).resolve()
    data_dir = run_dir / "data"
    work_dir = run_dir / "work"
    qa_dir = run_dir / "qa"
    for directory in (data_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=False)
    qa_dir.mkdir(parents=True, exist_ok=True)

    input_gpkg = Path(settings.input_gpkg).resolve()
    output_gpkg = data_dir / "cumulative_displacement_grid.gpkg"
    building_gpkg = data_dir / "cumulative_displacement_grid.building.gpkg"
    initial, periods = _catalog_for_selection(
        input_gpkg,
        settings.selected_fields,
    )
    selected_fields = tuple(item.field_name for item in periods)
    output_fields = tuple("M_" + field[2:] for field in selected_fields)

    _emit(progress, 1, _tr("计算输入GeoPackage哈希"))
    input_sha = _sha256_file(input_gpkg)
    connection = sqlite3.connect(
        f"file:{input_gpkg.as_posix()}?mode=ro",
        uri=True,
    )
    try:
        feature_count = int(
            connection.execute(
                f"SELECT COUNT(*) FROM {_quote_identifier(FULL_LAYER_NAME)}"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    if feature_count < 1:
        raise BatchCoreError(_tr("完整多时相点图层为空。"))
    period_count = len(periods)
    estimated_work = (
        feature_count * (16 + 4 * period_count + 8)
        + 512 * 1024 * 1024
    )
    if shutil.disk_usage(run_dir).free < estimated_work:
        raise BatchCoreError(
            _tr("可用空间不足；至少需要约{size:.2f} GiB。").format(
                size=estimated_work / 2**30
            )
        )

    x_path = work_dir / "x.float64"
    y_path = work_dir / "y.float64"
    delta_path = work_dir / "delta.float32"
    x_values = np.memmap(x_path, mode="w+", dtype=np.float64, shape=(feature_count,))
    y_values = np.memmap(y_path, mode="w+", dtype=np.float64, shape=(feature_count,))
    deltas = np.memmap(
        delta_path,
        mode="w+",
        dtype=np.float32,
        shape=(feature_count, period_count),
    )
    valid_counts = np.zeros(period_count, dtype=np.int64)
    invalid_counts = np.zeros(period_count, dtype=np.int64)
    full_min = np.full(period_count, np.inf, dtype=np.float64)
    full_max = np.full(period_count, -np.inf, dtype=np.float64)
    transformer = Transformer.from_crs(4326, 32650, always_xy=True)

    select_names = ["geom", initial.field_name, *selected_fields]
    sql = "SELECT " + ", ".join(
        _quote_identifier(name) for name in select_names
    ) + f" FROM {_quote_identifier(FULL_LAYER_NAME)} ORDER BY ps_uid"
    connection = sqlite3.connect(
        f"file:{input_gpkg.as_posix()}?mode=ro",
        uri=True,
    )
    offset = 0
    try:
        cursor = connection.execute(sql)
        while True:
            _check_cancelled(is_cancelled)
            rows = cursor.fetchmany(fetch_size)
            if not rows:
                break
            count = len(rows)
            coordinates = np.asarray(
                [parse_gpkg_point_xy(row[0]) for row in rows],
                dtype=np.float64,
            )
            projected_x, projected_y = transformer.transform(
                coordinates[:, 0],
                coordinates[:, 1],
            )
            x_values[offset : offset + count] = projected_x
            y_values[offset : offset + count] = projected_y
            initial_values = np.asarray(
                [np.nan if row[1] is None else row[1] for row in rows],
                dtype=np.float32,
            )
            target_values = np.asarray(
                [
                    [
                        np.nan if value is None else value
                        for value in row[2:]
                    ]
                    for row in rows
                ],
                dtype=np.float32,
            )
            batch_delta = target_values - initial_values[:, None]
            deltas[offset : offset + count, :] = batch_delta
            finite = np.isfinite(batch_delta)
            valid_counts += np.sum(finite, axis=0, dtype=np.int64)
            invalid_counts += count - np.sum(
                finite,
                axis=0,
                dtype=np.int64,
            )
            for index in range(period_count):
                values = batch_delta[:, index]
                values = values[np.isfinite(values)]
                if values.size:
                    full_min[index] = min(full_min[index], float(values.min()))
                    full_max[index] = max(full_max[index], float(values.max()))
            offset += count
            _emit(
                progress,
                5 + int(48 * offset / feature_count),
                _tr("读取并计算逐点差值：{offset:,}/{total:,}").format(
                    offset=offset, total=feature_count
                ),
            )
        if offset != feature_count:
            raise BatchCoreError(
                _tr("实际读取{actual:,}点，预期{expected:,}点。").format(
                    actual=offset, expected=feature_count
                )
            )
    finally:
        connection.close()
    x_values.flush()
    y_values.flush()
    deltas.flush()

    _check_cancelled(is_cancelled)
    grid_size = float(settings.grid_size_m)
    origin_x = math.floor(float(np.min(x_values)) / grid_size) * grid_size
    origin_y = math.floor(float(np.min(y_values)) / grid_size) * grid_size
    columns = np.floor((x_values - origin_x) / grid_size).astype(np.int32)
    rows = np.floor((y_values - origin_y) / grid_size).astype(np.int32)
    width = int(np.max(columns)) + 1
    height = int(np.max(rows)) + 1
    dense = rows.astype(np.int64) * width + columns.astype(np.int64)
    unique_dense, inverse, counts = np.unique(
        dense,
        return_inverse=True,
        return_counts=True,
    )
    occupied = int(unique_dense.size)
    order = np.argsort(inverse, kind="stable")
    starts = np.concatenate(
        (
            np.asarray([0], dtype=np.int64),
            np.cumsum(counts[:-1], dtype=np.int64),
        )
    )
    median_path = work_dir / "median.float32"
    medians = np.memmap(
        median_path,
        mode="w+",
        dtype=np.float32,
        shape=(occupied, period_count),
    )
    medians[:] = np.nan
    for cell_index, (start, count) in enumerate(zip(starts, counts)):
        if cell_index % 200 == 0:
            _check_cancelled(is_cancelled)
            _emit(
                progress,
                55 + int(21 * cell_index / max(1, occupied)),
                _tr("计算50米网格中位数：{index:,}/{total:,}").format(
                    index=cell_index, total=occupied
                ),
            )
        point_indices = order[start : start + count]
        group = np.asarray(deltas[point_indices, :], dtype=np.float32)
        with np.errstate(invalid="ignore"):
            medians[cell_index, :] = np.nanmedian(group, axis=0)
    medians.flush()

    summaries: list[PeriodGridSummary] = []
    for index, period in enumerate(periods):
        period_medians = np.asarray(medians[:, index])
        finite_medians = period_medians[np.isfinite(period_medians)]
        if finite_medians.size == 0:
            raise BatchCoreError(
                _tr("{field}没有有效网格中位数。").format(field=period.field_name)
            )
        summaries.append(
            PeriodGridSummary(
                source_field=period.field_name,
                output_field=output_fields[index],
                acquisition_date=period.acquisition_date,
                valid_point_count=int(valid_counts[index]),
                invalid_point_count=int(invalid_counts[index]),
                full_minimum_m=float(full_min[index]),
                full_maximum_m=float(full_max[index]),
                grid_median_minimum_m=float(finite_medians.min()),
                grid_median_maximum_m=float(finite_medians.max()),
            )
        )

    _write_grid_geopackage(
        building_gpkg,
        output_gpkg,
        unique_dense=unique_dense,
        counts=counts,
        medians=medians,
        period_summaries=summaries,
        initial=initial,
        origin_x=origin_x,
        origin_y=origin_y,
        width=width,
        height=height,
        grid_size_m=grid_size,
        progress=progress,
        is_cancelled=is_cancelled,
    )
    validation = _validate_grid_gpkg(output_gpkg, occupied, summaries)
    if not all(validation.values()):
        failed = [key for key, value in validation.items() if not value]
        raise BatchCoreError(
            _tr("派生GeoPackage质量门失败：{failed}").format(failed=failed)
        )

    _emit(progress, 90, _tr("复核输入未被修改并清理临时数组"))
    after_sha = _sha256_file(input_gpkg)
    if after_sha != input_sha:
        raise BatchCoreError(_tr("输入GeoPackage在任务期间发生变化。"))
    output_sha = _sha256_file(output_gpkg)
    result = GridBuildResult(
        output_gpkg=output_gpkg,
        feature_count=feature_count,
        occupied_cell_count=occupied,
        origin_x=origin_x,
        origin_y=origin_y,
        width=width,
        height=height,
        grid_size_m=grid_size,
        initial_field=initial.field_name,
        initial_date=initial.acquisition_date,
        periods=tuple(summaries),
        input_sha256=input_sha,
        output_sha256=output_sha,
        validation=validation,
    )
    _write_json(
        qa_dir / "grid_build_result.json",
        {
            **asdict(result),
            "output_gpkg": str(output_gpkg),
        },
    )

    try:
        del period_medians
        del finite_medians
    except UnboundLocalError:
        pass
    try:
        del group
    except UnboundLocalError:
        pass
    for array in (medians, deltas, x_values, y_values):
        array.flush()
        mmap_handle = getattr(array, "_mmap", None)
        if mmap_handle is not None:
            mmap_handle.close()
    del medians
    del deltas
    del x_values
    del y_values
    gc.collect()
    for path in (median_path, delta_path, x_path, y_path):
        path.unlink(missing_ok=True)
    try:
        work_dir.rmdir()
    except OSError:
        pass
    _emit(progress, 92, _tr("累计形变网格构建完成"))
    return result
