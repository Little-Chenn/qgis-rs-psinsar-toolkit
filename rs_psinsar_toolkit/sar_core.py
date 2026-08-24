"""Pure GDAL/OGR core for the staged M8.4 SAR workflow."""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
from osgeo import gdal, ogr, osr

from .localization import tr
from .version import SAR_PROCESSING_ENGINE_VERSION
from .sar_product_catalog import (
    build_catalog,
    catalog_summary,
    discover_rasters,
)


VERSION = SAR_PROCESSING_ENGINE_VERSION
NODATA_DEFAULT = -9999.0
CancelCallback = Callable[[], bool] | None
ProgressCallback = Callable[[int, str], None] | None
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)

gdal.UseExceptions()


class SarCancelled(RuntimeError):
    """Raised when a cooperative SAR task cancellation is observed."""


def _check_cancelled(is_cancelled: CancelCallback) -> None:
    if is_cancelled is not None and is_cancelled():
        raise SarCancelled(_tr("用户取消了SAR处理任务。"))


def _emit(
    progress: ProgressCallback,
    value: int,
    message: str,
) -> None:
    if progress is not None:
        progress(max(0, min(100, int(value))), message)


def sha256_file(
    path: Path,
    *,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
    progress_start: int = 0,
    progress_end: int = 100,
) -> str:
    digest = hashlib.sha256()
    size = max(1, path.stat().st_size)
    completed = 0
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            _check_cancelled(is_cancelled)
            digest.update(block)
            completed += len(block)
            value = progress_start + int(
                (progress_end - progress_start) * completed / size
            )
            _emit(progress, value, _tr("正在计算哈希：{name}").format(name=path.name))
    return digest.hexdigest()


def list_rasters(folder: str | Path) -> list[Path]:
    return discover_rasters(folder)


def _srs_from_wkt(wkt: str) -> osr.SpatialReference:
    if not wkt:
        raise ValueError(_tr("数据缺少坐标系。"))
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    if hasattr(srs, "SetAxisMappingStrategy"):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs


def _authid(srs: osr.SpatialReference) -> str:
    try:
        srs.AutoIdentifyEPSG()
    except Exception:
        pass
    authority = srs.GetAuthorityName(None)
    code = srs.GetAuthorityCode(None)
    if authority and code:
        return f"{authority}:{code}"
    return srs.GetName() or _tr("未知坐标系")


def _dataset_geotransform(dataset: gdal.Dataset) -> tuple[float, ...]:
    try:
        value = dataset.GetGeoTransform(can_return_null=True)
    except TypeError:
        value = dataset.GetGeoTransform()
    if value is None:
        raise ValueError(_tr("栅格缺少仿射变换。"))
    return tuple(float(item) for item in value)


def _bounds(
    width: int,
    height: int,
    geotransform: Sequence[float],
) -> dict[str, float]:
    corners = []
    for pixel, line in (
        (0, 0),
        (width, 0),
        (width, height),
        (0, height),
    ):
        x = (
            geotransform[0]
            + pixel * geotransform[1]
            + line * geotransform[2]
        )
        y = (
            geotransform[3]
            + pixel * geotransform[4]
            + line * geotransform[5]
        )
        corners.append((x, y))
    return {
        "xmin": min(item[0] for item in corners),
        "ymin": min(item[1] for item in corners),
        "xmax": max(item[0] for item in corners),
        "ymax": max(item[1] for item in corners),
    }


def _sample_statistics(dataset: gdal.Dataset) -> dict[str, Any]:
    band = dataset.GetRasterBand(1)
    sample_x = min(dataset.RasterXSize, 1024)
    sample_y = min(dataset.RasterYSize, 1024)
    array = band.ReadAsArray(
        0,
        0,
        dataset.RasterXSize,
        dataset.RasterYSize,
        buf_xsize=sample_x,
        buf_ysize=sample_y,
    )
    if array is None:
        raise RuntimeError(_tr("无法抽样读取栅格。"))
    array = np.asarray(array, dtype=np.float64)
    nodata = band.GetNoDataValue()
    valid = np.isfinite(array)
    if nodata is not None:
        valid &= ~np.isclose(array, nodata)
    values = array[valid]
    if values.size == 0:
        raise ValueError(_tr("栅格没有有效像元。"))
    return {
        "nodata": None if nodata is None else float(nodata),
        "sample_total_count": int(array.size),
        "sample_valid_count": int(values.size),
        "sample_nonfinite_count": int(np.count_nonzero(~np.isfinite(array))),
        "sample_valid_ratio": float(values.size / array.size),
        "sample_nonfinite_ratio": float(np.mean(~np.isfinite(array))),
        "sample_min": float(np.min(values)),
        "sample_max": float(np.max(values)),
        "sample_p02": float(np.percentile(values, 2.0)),
        "sample_median": float(np.median(values)),
        "sample_p98": float(np.percentile(values, 98.0)),
        "sample_positive_ratio": float(np.mean(values > 0)),
        "sample_zero_ratio": float(np.mean(values == 0)),
        "sample_negative_ratio": float(np.mean(values < 0)),
    }


def inspect_raster(path: str | Path) -> dict[str, Any]:
    path = Path(path).expanduser().resolve()
    dataset = gdal.OpenEx(str(path), gdal.OF_RASTER | gdal.OF_READONLY)
    if dataset is None:
        raise ValueError(_tr("GDAL无法打开栅格：{path}").format(path=path))
    if dataset.RasterCount < 1:
        dataset = None
        raise ValueError(_tr("栅格没有波段：{name}").format(name=path.name))
    band = dataset.GetRasterBand(1)
    geotransform = _dataset_geotransform(dataset)
    projection = dataset.GetProjectionRef() or ""
    srs = _srs_from_wkt(projection)
    result = {
        "path": str(path),
        "file": path.name,
        "width": int(dataset.RasterXSize),
        "height": int(dataset.RasterYSize),
        "band_count": int(dataset.RasterCount),
        "data_type": gdal.GetDataTypeName(band.DataType),
        "crs": _authid(srs),
        "projection_wkt": projection,
        "geotransform": list(geotransform),
        "x_resolution": abs(float(geotransform[1])),
        "y_resolution": abs(float(geotransform[5])),
        "bounds": _bounds(
            dataset.RasterXSize,
            dataset.RasterYSize,
            geotransform,
        ),
        "size_bytes": path.stat().st_size,
        **_sample_statistics(dataset),
    }
    dataset = None
    return result


def inspect_inputs(
    raster_paths: Sequence[Path],
    *,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    if len(raster_paths) < 1:
        raise ValueError(_tr("SAR处理至少需要一幅影像。"))
    if len({path.resolve() for path in raster_paths}) != len(raster_paths):
        raise ValueError(_tr("输入影像列表包含重复路径。"))

    records = []
    reference_srs = None
    union = {
        "xmin": math.inf,
        "ymin": math.inf,
        "xmax": -math.inf,
        "ymax": -math.inf,
    }
    product_catalog = build_catalog(raster_paths)
    for index, (path, product) in enumerate(
        zip(raster_paths, product_catalog), start=1
    ):
        _check_cancelled(is_cancelled)
        info = inspect_raster(path)
        if info["band_count"] != 1:
            raise ValueError(_tr("{name}不是单波段影像。").format(name=path.name))
        gt = info["geotransform"]
        if not math.isclose(gt[2], 0.0, abs_tol=1e-12) or not math.isclose(
            gt[4],
            0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(_tr("{name}含旋转项，当前版本不支持。").format(name=path.name))
        srs = _srs_from_wkt(info["projection_wkt"])
        if reference_srs is None:
            reference_srs = srs.Clone()
        elif not bool(reference_srs.IsSame(srs)):
            raise ValueError(_tr("{name}的CRS与第一幅影像不一致。").format(name=path.name))
        if info["sample_negative_ratio"] > 0:
            raise ValueError(
                _tr(
                    "{name}含有效负值，可能已是dB或语义不明；"
                    "当前版本拒绝自动10log10转换。"
                ).format(name=path.name)
            )
        if info["sample_positive_ratio"] <= 0:
            raise ValueError(
                _tr("{name}没有正值，不能执行线性功率转dB。").format(name=path.name)
            )
        for key in union:
            if key in {"xmin", "ymin"}:
                union[key] = min(union[key], info["bounds"][key])
            else:
                union[key] = max(union[key], info["bounds"][key])
        info["source_order"] = index
        info["product_metadata"] = product
        records.append(info)
        _emit(
            progress,
            int(100 * index / len(raster_paths)),
            _tr("已检查 {index}/{count}：{name}").format(
                index=index, count=len(raster_paths), name=path.name
            ),
        )
    assert reference_srs is not None
    assessment = scientific_assessment(records)
    return {
        "raster_count": len(records),
        "crs": _authid(reference_srs),
        "projection_wkt": reference_srs.ExportToWkt(),
        "union_bounds": union,
        "first_x_resolution": records[0]["x_resolution"],
        "first_y_resolution": records[0]["y_resolution"],
        "rasters": records,
        "product_catalog": product_catalog,
        "catalog_summary": catalog_summary(product_catalog),
        "scientific_assessment": assessment,
        "source_order_rule": (
            "explicit GUI order; later valid pixels overwrite earlier valid "
            "pixels; intrinsic source NoData does not overwrite valid data"
        ),
    }


def scientific_assessment(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return conservative scientific warnings without changing values."""

    warnings: list[str] = []
    errors: list[str] = []
    products = [item.get("product_metadata") or {} for item in records]
    polarisations = sorted(
        {
            str(item.get("polarisation"))
            for item in products
            if item.get("polarisation")
        }
    )
    passes = sorted(
        {
            str(item.get("pass_direction"))
            for item in products
            if item.get("pass_direction")
        }
    )
    if len(polarisations) > 1:
        errors.append(
            _tr("输入产品包含不同极化方式，不能直接镶嵌：{values}").format(
                values=", ".join(polarisations)
            )
        )
    mixed_orbit = len(passes) > 1
    if mixed_orbit:
        warnings.append(
            _tr("检测到升轨/降轨混合；默认应分组处理，强制混合必须由用户确认。")
        )

    incidence = [
        float(item["incidence_angle_mid_swath"])
        for item in products
        if item.get("incidence_angle_mid_swath") is not None
    ]
    incidence_span = max(incidence) - min(incidence) if incidence else None
    if incidence_span is not None and incidence_span > 3.0:
        warnings.append(
            _tr("入射角跨度为{span:.2f}°，可能造成明显辐射差异。").format(
                span=incidence_span
            )
        )

    median_db = []
    for item in records:
        value = float(item["sample_median"])
        median_db.append(10.0 * math.log10(value) if value > 0 else math.nan)
    finite_db = [value for value in median_db if math.isfinite(value)]
    reference_db = float(np.median(finite_db)) if finite_db else math.nan
    radiometric_outliers = []
    for item, value_db in zip(records, median_db):
        deviation = value_db - reference_db
        if math.isfinite(deviation) and abs(deviation) > 6.0:
            radiometric_outliers.append(
                {
                    "source_order": item["source_order"],
                    "file": item["file"],
                    "sample_median": item["sample_median"],
                    "median_db": value_db,
                    "deviation_from_group_median_db": deviation,
                }
            )
    radiometric_warning = bool(radiometric_outliers)
    if radiometric_warning:
        warnings.append(
            _tr(
                "检测到中位强度相对组中位数偏差超过6 dB的影像；"
                "仅报警，不自动剔除或归一化。"
            )
        )

    nan_without_nodata = [
        {
            "source_order": item["source_order"],
            "file": item["file"],
            "sample_nonfinite_ratio": item["sample_nonfinite_ratio"],
        }
        for item in records
        if item["nodata"] is None and item["sample_nonfinite_ratio"] > 0.0
    ]
    if nan_without_nodata:
        warnings.append(
            _tr("存在未声明NoData的NaN边缘；处理时将使用临时VRT保护有效像元。")
        )

    calibration_count = sum(
        bool(item.get("calibration_metadata_present")) for item in products
    )
    calibrated = bool(products) and calibration_count == len(products)
    if products and not calibrated:
        warnings.append(
            _tr("未发现完整Sigma0/Gamma0等辐射定标信息；输出语义限定为“强度dB”。")
        )

    return {
        "status": "REJECTED" if errors else ("WARNING" if warnings else "PASS"),
        "errors": errors,
        "warnings": warnings,
        "polarisations": polarisations,
        "pass_directions": passes,
        "mixed_orbit_directions": mixed_orbit,
        "incidence_angle_span_degrees": incidence_span,
        "radiometric_reference_median_db": reference_db,
        "radiometric_outliers": radiometric_outliers,
        "radiometric_warning": radiometric_warning,
        "nan_without_declared_nodata": nan_without_nodata,
        "nan_protection_required": bool(nan_without_nodata),
        "calibration_metadata_complete": calibrated,
        "recommended_db_label": (
            "calibrated backscatter (dB)" if calibrated else "intensity (dB)"
        ),
    }


def estimate_float32_grid(
    bounds: dict[str, float],
    x_resolution: float,
    y_resolution: float,
) -> dict[str, Any]:
    width = max(
        1,
        int(math.ceil((bounds["xmax"] - bounds["xmin"]) / x_resolution)),
    )
    height = max(
        1,
        int(math.ceil((bounds["ymax"] - bounds["ymin"]) / y_resolution)),
    )
    pixels = width * height
    bytes_one = pixels * 4
    return {
        "width": width,
        "height": height,
        "pixel_count": pixels,
        "float32_bytes_one_raster": bytes_one,
        "float32_gib_one_raster": bytes_one / (1024**3),
        "three_stage_uncompressed_gib": bytes_one * 3 / (1024**3),
    }


def validate_mask(
    mask_path: str | Path,
    raster_projection_wkt: str,
) -> dict[str, Any]:
    mask_path = Path(mask_path).expanduser().resolve()
    if not mask_path.is_file():
        raise ValueError(_tr("裁剪面不存在：{path}").format(path=mask_path))
    dataset = ogr.Open(str(mask_path), 0)
    if dataset is None:
        raise ValueError(_tr("OGR无法打开裁剪面。"))
    layer = dataset.GetLayer(0)
    if layer is None or layer.GetFeatureCount() <= 0:
        dataset = None
        raise ValueError(_tr("裁剪数据中没有可用要素。"))
    geometry_type = layer.GetGeomType()
    if hasattr(ogr, "GT_Flatten"):
        geometry_type = ogr.GT_Flatten(geometry_type)
    elif hasattr(ogr, "wkbFlatten"):
        geometry_type = ogr.wkbFlatten(geometry_type)
    if geometry_type not in {ogr.wkbPolygon, ogr.wkbMultiPolygon}:
        dataset = None
        raise ValueError(_tr("裁剪图层必须是Polygon或MultiPolygon。"))
    layer_srs = layer.GetSpatialRef()
    if layer_srs is None:
        dataset = None
        raise ValueError(_tr("裁剪图层没有坐标系。"))
    if hasattr(layer_srs, "SetAxisMappingStrategy"):
        layer_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    raster_srs = _srs_from_wkt(raster_projection_wkt)
    if not bool(layer_srs.IsSame(raster_srs)):
        actual = _authid(layer_srs)
        expected = _authid(raster_srs)
        dataset = None
        raise ValueError(
            _tr("裁剪面CRS与栅格不一致：{actual}；栅格为{expected}。").format(
                actual=actual, expected=expected
            )
        )
    extent = layer.GetExtent()
    result = {
        "path": str(mask_path),
        "layer_name": layer.GetName(),
        "feature_count": int(layer.GetFeatureCount()),
        "crs": _authid(layer_srs),
        "bounds": {
            "xmin": float(extent[0]),
            "ymin": float(extent[2]),
            "xmax": float(extent[1]),
            "ymax": float(extent[3]),
        },
        "size_bytes": mask_path.stat().st_size,
    }
    dataset = None
    return result


def rectangles_intersect(a: dict, b: dict) -> bool:
    return not (
        a["xmax"] <= b["xmin"]
        or a["xmin"] >= b["xmax"]
        or a["ymax"] <= b["ymin"]
        or a["ymin"] >= b["ymax"]
    )


def _warp_callback(
    progress: ProgressCallback,
    is_cancelled: CancelCallback,
    message: str,
) -> Callable[[float, str, object], int]:
    def callback(fraction, detail, _data):
        _emit(
            progress,
            int(float(fraction) * 100),
            detail or message,
        )
        return 0 if is_cancelled is not None and is_cancelled() else 1

    return callback


def _replace_partial(
    partial_path: Path,
    output_path: Path,
) -> None:
    if output_path.exists():
        raise FileExistsError(_tr("输出已存在：{path}").format(path=output_path))
    partial_path.replace(output_path)


def _nan_safe_warp_sources(
    input_paths: Sequence[Path],
    inspection: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Attach NaN NoData in temporary VRTs without editing source rasters."""

    info_by_path = {
        str(Path(item["path"]).resolve()): item
        for item in inspection["rasters"]
    }
    sources: list[str] = []
    temporary_vrts: list[str] = []
    for index, path in enumerate(input_paths, start=1):
        resolved = str(path.resolve())
        info = info_by_path[resolved]
        if info.get("nodata") is not None:
            sources.append(resolved)
            continue
        vrt_path = (
            f"/vsimem/rs-psinsar-m83-{os.getpid()}-{index}-nan-safe.vrt"
        )
        translated = gdal.Translate(
            vrt_path,
            resolved,
            options=gdal.TranslateOptions(format="VRT", noData=float("nan")),
        )
        if translated is None:
            for existing in temporary_vrts:
                gdal.Unlink(existing)
            raise RuntimeError(
                _tr("无法为NaN保护创建临时VRT：{name}").format(name=path.name)
            )
        translated.FlushCache()
        translated = None
        sources.append(vrt_path)
        temporary_vrts.append(vrt_path)
    return sources, temporary_vrts


def mosaic_to_common_grid(
    input_paths: Sequence[Path],
    output_path: str | Path,
    inspection: dict[str, Any],
    *,
    x_resolution: float,
    y_resolution: float,
    resampling: str,
    output_nodata: float,
    output_bounds: dict[str, float] | None = None,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(_tr("输出已存在：{path}").format(path=output_path))
    partial = output_path.with_name(f".{output_path.stem}.partial.tif")
    if partial.exists():
        raise FileExistsError(_tr("临时输出已存在：{path}").format(path=partial))
    _check_cancelled(is_cancelled)
    requested_bounds = output_bounds or inspection["union_bounds"]
    xmin = math.floor(requested_bounds["xmin"] / x_resolution) * x_resolution
    ymin = math.floor(requested_bounds["ymin"] / y_resolution) * y_resolution
    xmax = math.ceil(requested_bounds["xmax"] / x_resolution) * x_resolution
    ymax = math.ceil(requested_bounds["ymax"] / y_resolution) * y_resolution
    width = max(1, int(round((xmax - xmin) / x_resolution)))
    height = max(1, int(round((ymax - ymin) / y_resolution)))
    driver = gdal.GetDriverByName("GTiff")
    target = driver.Create(
        str(partial),
        width,
        height,
        1,
        gdal.GDT_Float32,
        options=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"],
    )
    if target is None:
        raise RuntimeError(_tr("无法创建镶嵌临时输出。"))
    target.SetProjection(inspection["projection_wkt"])
    target.SetGeoTransform((xmin, x_resolution, 0.0, ymax, 0.0, -y_resolution))
    target_band = target.GetRasterBand(1)
    target_band.SetNoDataValue(output_nodata)
    target_band.Fill(output_nodata)
    target_band.FlushCache()
    warp_sources, temporary_vrts = _nan_safe_warp_sources(
        input_paths,
        inspection,
    )
    try:
        source_count = len(warp_sources)
        for source_index, source in enumerate(warp_sources):
            _check_cancelled(is_cancelled)

            def scaled_progress(value: int, message: str) -> None:
                _emit(
                    progress,
                    int(
                        100
                        * (source_index + value / 100.0)
                        / source_count
                    ),
                    message,
                )

            options = gdal.WarpOptions(
                dstSRS=inspection["projection_wkt"],
                dstNodata=output_nodata,
                resampleAlg=resampling,
                multithread=True,
                warpOptions=[
                    "NUM_THREADS=ALL_CPUS",
                    "UNIFIED_SRC_NODATA=YES",
                ],
                callback=_warp_callback(
                    scaled_progress,
                    is_cancelled,
                    _tr("正在写入第{index}/{count}景……").format(
                        index=source_index + 1, count=source_count
                    ),
                ),
            )
            result = gdal.Warp(target, source, options=options)
            if result is None or result == 0:
                raise RuntimeError(
                    _tr("GDAL写入第{index}景失败。").format(index=source_index + 1)
                )
            target.FlushCache()
    except RuntimeError as exc:
        target = None
        if is_cancelled is not None and is_cancelled():
            raise SarCancelled(_tr("用户在镶嵌过程中取消了任务。")) from exc
        raise
    finally:
        for vrt_path in temporary_vrts:
            gdal.Unlink(vrt_path)
    target.SetMetadataItem(
        "SOURCE_ORDER_RULE",
        "later valid source pixels overwrite earlier valid source pixels",
    )
    target.SetMetadataItem("RESAMPLING", resampling)
    target.SetMetadataItem("WRITE_MODE", "sequential-valid-pixel-overlay")
    target.FlushCache()
    target = None
    _check_cancelled(is_cancelled)
    inspect_raster(partial)
    _replace_partial(partial, output_path)
    return inspect_raster(output_path)


def clip_mosaic(
    mosaic_path: str | Path,
    mask_path: str | Path,
    output_path: str | Path,
    *,
    resampling: str,
    output_nodata: float,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(_tr("输出已存在：{path}").format(path=output_path))
    partial = output_path.with_name(f".{output_path.stem}.partial.tif")
    if partial.exists():
        raise FileExistsError(_tr("临时输出已存在：{path}").format(path=partial))
    _check_cancelled(is_cancelled)
    options = gdal.WarpOptions(
        format="GTiff",
        cutlineDSName=str(mask_path),
        cropToCutline=True,
        srcNodata=output_nodata,
        dstNodata=output_nodata,
        resampleAlg=resampling,
        multithread=True,
        warpOptions=["NUM_THREADS=ALL_CPUS", "UNIFIED_SRC_NODATA=YES"],
        creationOptions=[
            "COMPRESS=LZW",
            "TILED=YES",
            "BIGTIFF=IF_SAFER",
        ],
        callback=_warp_callback(
            progress,
            is_cancelled,
            _tr("正在按掩膜裁剪……"),
        ),
    )
    try:
        result = gdal.Warp(
            str(partial),
            str(mosaic_path),
            options=options,
        )
    except RuntimeError as exc:
        if is_cancelled is not None and is_cancelled():
            raise SarCancelled(_tr("用户在裁剪过程中取消了任务。")) from exc
        raise
    if result is None:
        raise RuntimeError(_tr("GDAL裁剪失败。"))
    result.FlushCache()
    result = None
    _check_cancelled(is_cancelled)
    inspect_raster(partial)
    _replace_partial(partial, output_path)
    return inspect_raster(output_path)


def linear_power_to_db(
    input_path: str | Path,
    output_path: str | Path,
    *,
    output_nodata: float,
    value_semantics: str = "intensity (dB)",
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(_tr("输出已存在：{path}").format(path=output_path))
    partial = output_path.with_name(f".{output_path.stem}.partial.tif")
    if partial.exists():
        raise FileExistsError(_tr("临时输出已存在：{path}").format(path=partial))
    source = gdal.OpenEx(
        str(input_path),
        gdal.OF_RASTER | gdal.OF_READONLY,
    )
    if source is None or source.RasterCount != 1:
        raise ValueError(_tr("dB转换要求有效单波段栅格。"))
    driver = gdal.GetDriverByName("GTiff")
    target = driver.Create(
        str(partial),
        source.RasterXSize,
        source.RasterYSize,
        1,
        gdal.GDT_Float32,
        options=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"],
    )
    if target is None:
        source = None
        raise RuntimeError(_tr("无法创建dB临时输出。"))
    target.SetGeoTransform(source.GetGeoTransform())
    target.SetProjection(source.GetProjection())
    source_band = source.GetRasterBand(1)
    target_band = target.GetRasterBand(1)
    target_band.SetNoDataValue(output_nodata)
    semantic_text = str(value_semantics).strip() or "intensity (dB)"
    target_band.SetDescription(f"SAR {semantic_text}")
    source_nodata = source_band.GetNoDataValue()
    block_x, block_y = source_band.GetBlockSize()
    if block_x <= 0 or block_y <= 0:
        block_x, block_y = 512, 512
    valid_count = 0
    finite_linear_count = 0
    negative_linear_count = 0
    zero_linear_count = 0
    total_blocks = math.ceil(source.RasterXSize / block_x) * math.ceil(
        source.RasterYSize / block_y
    )
    completed = 0
    for y_offset in range(0, source.RasterYSize, block_y):
        y_size = min(block_y, source.RasterYSize - y_offset)
        for x_offset in range(0, source.RasterXSize, block_x):
            _check_cancelled(is_cancelled)
            x_size = min(block_x, source.RasterXSize - x_offset)
            array = source_band.ReadAsArray(
                x_offset,
                y_offset,
                x_size,
                y_size,
            )
            if array is None:
                target = None
                source = None
                raise RuntimeError(_tr("读取线性栅格块失败。"))
            array = np.asarray(array, dtype=np.float32)
            finite = np.isfinite(array)
            if source_nodata is not None:
                finite &= ~np.isclose(array, source_nodata)
            valid = finite & (array > 0)
            finite_linear_count += int(np.count_nonzero(finite))
            negative_linear_count += int(
                np.count_nonzero(finite & (array < 0))
            )
            zero_linear_count += int(
                np.count_nonzero(finite & (array == 0))
            )
            output = np.full(array.shape, output_nodata, dtype=np.float32)
            output[valid] = 10.0 * np.log10(array[valid])
            valid_count += int(np.count_nonzero(valid))
            target_band.WriteArray(output, x_offset, y_offset)
            completed += 1
            _emit(
                progress,
                int(100 * completed / total_blocks),
                _tr("正在执行10log10线性功率转dB……"),
            )
    if valid_count == 0:
        target = None
        source = None
        raise ValueError(_tr("裁剪结果没有正值，无法转换为dB。"))
    target.SetMetadata(
        {
            "UNIT": "dB",
            "CONVERSION": "10*log10(linear_power)",
            "VALUE_SEMANTICS": semantic_text,
            "SOURCE": str(input_path),
            "VALID_PIXEL_COUNT": str(valid_count),
            "FINITE_LINEAR_PIXEL_COUNT": str(finite_linear_count),
            "NEGATIVE_LINEAR_PIXEL_COUNT": str(negative_linear_count),
            "ZERO_LINEAR_PIXEL_COUNT": str(zero_linear_count),
        }
    )
    target_band.FlushCache()
    target.FlushCache()
    target = None
    source = None
    _check_cancelled(is_cancelled)
    inspect_raster(partial)
    _replace_partial(partial, output_path)
    info = inspect_raster(output_path)
    info["valid_pixel_count"] = valid_count
    info["finite_linear_pixel_count"] = finite_linear_count
    info["negative_linear_pixel_count"] = negative_linear_count
    info["zero_linear_pixel_count"] = zero_linear_count
    info["nonpositive_linear_pixel_count"] = (
        negative_linear_count + zero_linear_count
    )
    return info


def sampled_percentiles(
    raster_path: str | Path,
    low: float,
    high: float,
) -> tuple[float, float]:
    if not 0 <= low < high <= 100:
        raise ValueError(_tr("显示分位数必须满足0≤低值<高值≤100。"))
    dataset = gdal.OpenEx(
        str(raster_path),
        gdal.OF_RASTER | gdal.OF_READONLY,
    )
    if dataset is None:
        raise ValueError(_tr("无法读取dB栅格：{path}").format(path=raster_path))
    band = dataset.GetRasterBand(1)
    array = band.ReadAsArray(
        0,
        0,
        dataset.RasterXSize,
        dataset.RasterYSize,
        buf_xsize=min(dataset.RasterXSize, 2048),
        buf_ysize=min(dataset.RasterYSize, 2048),
    )
    nodata = band.GetNoDataValue()
    values = np.asarray(array, dtype=np.float64)
    valid = np.isfinite(values)
    if nodata is not None:
        valid &= ~np.isclose(values, nodata)
    values = values[valid]
    dataset = None
    if values.size == 0:
        raise ValueError(_tr("dB栅格没有有效像元。"))
    low_value, high_value = np.percentile(values, [low, high])
    if (
        not np.isfinite(low_value)
        or not np.isfinite(high_value)
        or low_value >= high_value
    ):
        raise ValueError(_tr("显示拉伸范围无效或数据缺少变化。"))
    return float(low_value), float(high_value)


DISPLAY_METHODS = {
    "percentile",
    "minmax",
    "stddev",
    "equalize",
    "centered",
}
COLOR_MODES = {"grayscale", "pseudocolor"}
COLOR_RAMPS = {"viridis", "spectral", "terrain", "plasma"}


def sampled_display_statistics(
    raster_path: str | Path,
    *,
    method: str,
    low_percentile: float = 2.0,
    high_percentile: float = 98.0,
) -> dict[str, Any]:
    """Calculate reproducible display-only statistics from a bounded sample."""

    if method not in DISPLAY_METHODS:
        raise ValueError(_tr("无法识别显示增强方法：{method}").format(method=method))
    dataset = gdal.OpenEx(str(raster_path), gdal.OF_RASTER | gdal.OF_READONLY)
    if dataset is None or dataset.RasterCount != 1:
        raise ValueError(_tr("无法读取单波段显示源：{path}").format(path=raster_path))
    band = dataset.GetRasterBand(1)
    array = band.ReadAsArray(
        0,
        0,
        dataset.RasterXSize,
        dataset.RasterYSize,
        buf_xsize=min(dataset.RasterXSize, 2048),
        buf_ysize=min(dataset.RasterYSize, 2048),
    )
    nodata = band.GetNoDataValue()
    sample = np.asarray(array, dtype=np.float64)
    valid = np.isfinite(sample)
    if nodata is not None:
        valid &= ~np.isclose(sample, nodata)
    values = sample[valid]
    dataset = None
    if values.size == 0:
        raise ValueError(_tr("显示源没有有效像元。"))
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    mean = float(np.mean(values))
    stddev = float(np.std(values))
    if method == "percentile":
        display_min, display_max = np.percentile(
            values, [low_percentile, high_percentile]
        )
    elif method == "minmax":
        display_min, display_max = minimum, maximum
    elif method == "stddev":
        display_min, display_max = mean - 2.0 * stddev, mean + 2.0 * stddev
    elif method == "centered":
        display_min, display_max = mean - 3.0 * stddev, mean + 3.0 * stddev
    else:
        display_min, display_max = minimum, maximum
    if not math.isfinite(display_min) or not math.isfinite(display_max):
        raise ValueError(_tr("显示统计含非有限数值。"))
    if display_max <= display_min:
        display_max = display_min + 1.0
    histogram, edges = np.histogram(values, bins=1024, range=(minimum, maximum))
    cumulative = np.cumsum(histogram, dtype=np.float64)
    if cumulative[-1] > 0:
        cumulative /= cumulative[-1]
    return {
        "method": method,
        "sample_count": int(values.size),
        "source_minimum": minimum,
        "source_maximum": maximum,
        "source_mean": mean,
        "source_stddev": stddev,
        "display_minimum": float(display_min),
        "display_maximum": float(display_max),
        "histogram_edges": edges.tolist(),
        "histogram_cdf": cumulative.tolist(),
    }


def _apply_display_curve(
    array: np.ndarray,
    valid: np.ndarray,
    statistics: dict[str, Any],
    *,
    brightness: int,
    contrast: int,
    gamma: float,
) -> np.ndarray:
    method = str(statistics["method"])
    if method == "equalize":
        edges = np.asarray(statistics["histogram_edges"], dtype=np.float64)
        cdf = np.asarray(statistics["histogram_cdf"], dtype=np.float64)
        normalised = np.interp(array, edges[1:], cdf, left=0.0, right=1.0)
    else:
        low = float(statistics["display_minimum"])
        high = float(statistics["display_maximum"])
        normalised = (array - low) / (high - low)
    normalised = np.clip(normalised, 0.0, 1.0)
    normalised = np.clip(normalised + brightness / 100.0, 0.0, 1.0)
    contrast_value = max(-99, min(99, int(contrast)))
    contrast_scale = (100.0 + contrast_value) / (100.0 - contrast_value)
    normalised = np.clip(
        (normalised - 0.5) * contrast_scale + 0.5,
        0.0,
        1.0,
    )
    normalised = np.power(normalised, 1.0 / float(gamma))
    return np.where(valid, normalised, 0.0)


def _colourise(normalised: np.ndarray, ramp: str) -> tuple[np.ndarray, ...]:
    ramps = {
        "viridis": (
            (0.0, (68, 1, 84)),
            (0.33, (49, 104, 142)),
            (0.66, (53, 183, 121)),
            (1.0, (253, 231, 37)),
        ),
        "spectral": (
            (0.0, (94, 79, 162)),
            (0.25, (50, 136, 189)),
            (0.5, (255, 255, 191)),
            (0.75, (244, 109, 67)),
            (1.0, (158, 1, 66)),
        ),
        "terrain": (
            (0.0, (40, 80, 160)),
            (0.35, (70, 160, 120)),
            (0.7, (210, 190, 120)),
            (1.0, (255, 255, 255)),
        ),
        "plasma": (
            (0.0, (13, 8, 135)),
            (0.33, (156, 23, 158)),
            (0.66, (237, 121, 83)),
            (1.0, (240, 249, 33)),
        ),
    }
    stops = ramps[ramp]
    positions = np.asarray([item[0] for item in stops], dtype=np.float64)
    channels = []
    for channel in range(3):
        values = np.asarray([item[1][channel] for item in stops], dtype=np.float64)
        channels.append(np.interp(normalised, positions, values).astype(np.uint8))
    return tuple(channels)


def create_display_product(
    input_path: str | Path,
    output_path: str | Path,
    *,
    statistics: dict[str, Any],
    color_mode: str = "grayscale",
    color_ramp: str = "viridis",
    brightness: int = 0,
    contrast: int = 0,
    gamma: float = 1.0,
    feather_pixels: int = 0,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    """Write an RGBA 8-bit visualization product without altering input."""

    if color_mode not in COLOR_MODES:
        raise ValueError(_tr("无法识别颜色模式：{mode}").format(mode=color_mode))
    if color_ramp not in COLOR_RAMPS:
        raise ValueError(_tr("无法识别伪彩色色带：{ramp}").format(ramp=color_ramp))
    if not -100 <= brightness <= 100 or not -99 <= contrast <= 99:
        raise ValueError(_tr("亮度须为-100—100，对比度须为-99—99。"))
    if not math.isfinite(gamma) or gamma <= 0.0:
        raise ValueError(_tr("Gamma必须为正数。"))
    if feather_pixels < 0 or feather_pixels > 1000:
        raise ValueError(_tr("基础外缘羽化距离必须为0—1000像素。"))
    source = gdal.OpenEx(str(input_path), gdal.OF_RASTER | gdal.OF_READONLY)
    if source is None or source.RasterCount != 1:
        raise ValueError(_tr("8位显示产品要求有效单波段栅格。"))
    output_path = Path(output_path)
    if output_path.exists():
        source = None
        raise FileExistsError(_tr("输出已存在：{path}").format(path=output_path))
    partial = output_path.with_name(f".{output_path.stem}.partial.tif")
    mask_path = output_path.with_name(f".{output_path.stem}.mask.tif")
    proximity_path = output_path.with_name(f".{output_path.stem}.proximity.tif")
    for temporary in (partial, mask_path, proximity_path):
        if temporary.exists():
            source = None
            raise FileExistsError(_tr("临时输出已存在：{path}").format(path=temporary))
    driver = gdal.GetDriverByName("GTiff")
    target = driver.Create(
        str(partial), source.RasterXSize, source.RasterYSize, 4, gdal.GDT_Byte,
        options=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"],
    )
    target.SetGeoTransform(source.GetGeoTransform())
    target.SetProjection(source.GetProjection())
    for index, interpretation in enumerate(
        (gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand, gdal.GCI_AlphaBand),
        start=1,
    ):
        target.GetRasterBand(index).SetColorInterpretation(interpretation)
    source_band = source.GetRasterBand(1)
    nodata = source_band.GetNoDataValue()
    block_x, block_y = source_band.GetBlockSize()
    if block_x <= 0 or block_y <= 0:
        block_x, block_y = 512, 512
    mask_dataset = None
    if feather_pixels > 0:
        mask_dataset = driver.Create(
            str(mask_path), source.RasterXSize, source.RasterYSize, 1, gdal.GDT_Byte,
            options=["COMPRESS=DEFLATE", "TILED=YES"],
        )
        mask_dataset.SetGeoTransform(source.GetGeoTransform())
        mask_dataset.SetProjection(source.GetProjection())
    blocks = math.ceil(source.RasterXSize / block_x) * math.ceil(source.RasterYSize / block_y)
    completed = 0
    for y_offset in range(0, source.RasterYSize, block_y):
        y_size = min(block_y, source.RasterYSize - y_offset)
        for x_offset in range(0, source.RasterXSize, block_x):
            _check_cancelled(is_cancelled)
            x_size = min(block_x, source.RasterXSize - x_offset)
            array = np.asarray(
                source_band.ReadAsArray(x_offset, y_offset, x_size, y_size),
                dtype=np.float64,
            )
            valid = np.isfinite(array)
            if nodata is not None:
                valid &= ~np.isclose(array, nodata)
            normalised = _apply_display_curve(
                array, valid, statistics,
                brightness=brightness, contrast=contrast, gamma=gamma,
            )
            if color_mode == "grayscale":
                grey = np.rint(normalised * 255.0).astype(np.uint8)
                red = green = blue = grey
            else:
                red, green, blue = _colourise(normalised, color_ramp)
            alpha = np.where(valid, 255, 0).astype(np.uint8)
            for index, channel in enumerate((red, green, blue, alpha), start=1):
                target.GetRasterBand(index).WriteArray(channel, x_offset, y_offset)
            if mask_dataset is not None:
                mask_dataset.GetRasterBand(1).WriteArray(
                    valid.astype(np.uint8), x_offset, y_offset
                )
            completed += 1
            _emit(
                progress,
                int(70 * completed / blocks),
                _tr("正在生成8位显示产品……"),
            )
    if mask_dataset is not None:
        mask_dataset.FlushCache()
        proximity = driver.Create(
            str(proximity_path), source.RasterXSize, source.RasterYSize, 1,
            gdal.GDT_Float32, options=["COMPRESS=DEFLATE", "TILED=YES"],
        )
        proximity.SetGeoTransform(source.GetGeoTransform())
        proximity.SetProjection(source.GetProjection())
        gdal.ComputeProximity(
            mask_dataset.GetRasterBand(1), proximity.GetRasterBand(1),
            options=["VALUES=0", "DISTUNITS=PIXEL", f"MAXDIST={feather_pixels}"],
        )
        for y_offset in range(0, source.RasterYSize, block_y):
            y_size = min(block_y, source.RasterYSize - y_offset)
            for x_offset in range(0, source.RasterXSize, block_x):
                x_size = min(block_x, source.RasterXSize - x_offset)
                mask = mask_dataset.GetRasterBand(1).ReadAsArray(
                    x_offset, y_offset, x_size, y_size
                ).astype(bool)
                distance = proximity.GetRasterBand(1).ReadAsArray(
                    x_offset, y_offset, x_size, y_size
                )
                alpha = np.where(
                    mask,
                    np.clip(distance / max(1, feather_pixels), 0.0, 1.0) * 255.0,
                    0.0,
                ).astype(np.uint8)
                target.GetRasterBand(4).WriteArray(alpha, x_offset, y_offset)
        proximity = None
        mask_dataset = None
    target.SetMetadata(
        {
            "PURPOSE": "8-bit visualization only; scientific source unchanged",
            "DISPLAY_METHOD": str(statistics["method"]),
            "COLOR_MODE": color_mode,
            "COLOR_RAMP": color_ramp if color_mode == "pseudocolor" else "none",
            "BRIGHTNESS": str(brightness),
            "CONTRAST": str(contrast),
            "GAMMA": str(gamma),
            "EDGE_FEATHER_PIXELS": str(feather_pixels),
            "SOURCE": str(Path(input_path).resolve()),
        }
    )
    target.FlushCache()
    target = None
    source = None
    for temporary in (mask_path, proximity_path):
        if temporary.exists():
            temporary.unlink()
    partial.replace(output_path)
    _emit(progress, 100, _tr("8位显示产品生成完成。"))
    return inspect_raster(output_path)


def grids_equal(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return (
        first["width"] == second["width"]
        and first["height"] == second["height"]
        and first["crs"] == second["crs"]
        and np.allclose(
            first["geotransform"],
            second["geotransform"],
            rtol=0.0,
            atol=1e-9,
        )
    )
