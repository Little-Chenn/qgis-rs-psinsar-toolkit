"""Non-overwriting workflow for real external-GCP geometric correction."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .geometry_core import (
    GeometryCancelled,
    ensure_new_run_directory,
    inspect_raster,
    write_json,
)
from .geometry_real_core import (
    MODEL_SPECS,
    RealControlPoint,
    calculate_residuals,
    fit_transform_model,
    georeference_with_external_gcps,
    localized_model_label,
    read_control_points,
    render_real_geometry_preview,
    spatial_reference,
    validate_real_control_points,
    write_control_points,
    write_rows,
)
from .localization import language_code, tr


TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


@dataclass(frozen=True)
class RealGeometryJobSettings:
    source_path: str
    training_points_path: str
    check_points_path: str
    output_root: str
    target_crs: str = "EPSG:32650"
    transform_model: str = "affine"
    resampling: str = "bilinear"
    x_resolution: float = 0.0
    y_resolution: float = 0.0
    check_rmse_threshold_pixel: float = 0.0
    acknowledge_external_points: bool = False
    load_result: bool = True


@dataclass(frozen=True)
class RealGeometryJobResult:
    run_dir: Path
    output_path: Path
    report_path: Path
    status: str
    train_rmse_pixel: float
    check_rmse_pixel: float
    check_max_error_pixel: float


def default_real_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_real_geometry")


def validate_real_geometry_settings(settings: RealGeometryJobSettings) -> list[str]:
    errors: list[str] = []
    if not settings.source_path.strip():
        errors.append(_tr("请选择待校正原始影像。"))
    if not settings.training_points_path.strip():
        errors.append(_tr("请选择训练GCP文件。"))
    if not settings.check_points_path.strip():
        errors.append(_tr("请选择独立检查点文件。"))
    if not settings.output_root.strip():
        errors.append(_tr("请选择输出根目录。"))
    if settings.resampling not in {"near", "bilinear", "cubic"}:
        errors.append(
            _tr("不支持的重采样方法：{resampling}").format(
                resampling=settings.resampling
            )
        )
    if settings.transform_model not in MODEL_SPECS:
        errors.append(
            _tr("不支持的几何变换模型：{model}").format(
                model=settings.transform_model
            )
        )
    if (settings.x_resolution > 0.0) != (settings.y_resolution > 0.0):
        errors.append(_tr("目标X/Y分辨率必须同时为0（自动）或同时大于0。"))
    if settings.x_resolution < 0.0 or settings.y_resolution < 0.0:
        errors.append(_tr("目标分辨率不能为负数。"))
    if settings.check_rmse_threshold_pixel < 0.0:
        errors.append(_tr("检查点RMSE阈值不能为负数。"))
    if not settings.acknowledge_external_points:
        errors.append(
            _tr(
                "请确认训练GCP和检查点来自独立外部参考，"
                "并理解本模式不等同于SAR轨道/地形校正。"
            )
        )
    return errors


def preflight_real_geometry_input(settings: RealGeometryJobSettings) -> dict[str, Any]:
    errors = validate_real_geometry_settings(settings)
    warnings: list[str] = []
    source_info: dict[str, Any] | None = None
    train: list[RealControlPoint] = []
    check: list[RealControlPoint] = []
    train_meta: dict[str, Any] | None = None
    check_meta: dict[str, Any] | None = None
    point_validation: dict[str, Any] | None = None

    try:
        if settings.source_path.strip():
            source_info = inspect_raster(Path(settings.source_path))
            if source_info["band_count"] < 1:
                errors.append(_tr("待校正影像没有可用波段。"))
            if source_info["width"] <= 1 or source_info["height"] <= 1:
                errors.append(_tr("待校正影像尺寸过小。"))
            if source_info["projection_wkt"] or source_info["geotransform"] is not None:
                warnings.append(
                    _tr(
                        "输入影像已有空间参考；本模式仍会以外部GCP重新解算，"
                        "原文件不会被覆盖。"
                    )
                )
    except Exception as exc:
        errors.append(str(exc))

    try:
        if settings.target_crs.strip():
            target_srs = spatial_reference(settings.target_crs)
            target_crs_wkt = target_srs.ExportToWkt()
        else:
            errors.append(_tr("请输入目标坐标系。"))
            target_crs_wkt = ""
    except Exception as exc:
        errors.append(str(exc))
        target_crs_wkt = ""

    try:
        if settings.training_points_path.strip():
            train, train_meta = read_control_points(
                Path(settings.training_points_path), "train"
            )
    except Exception as exc:
        errors.append(str(exc))
    try:
        if settings.check_points_path.strip():
            check, check_meta = read_control_points(
                Path(settings.check_points_path), "check"
            )
    except Exception as exc:
        errors.append(str(exc))

    if source_info is not None and train and check:
        point_validation = validate_real_control_points(
            train,
            check,
            int(source_info["width"]),
            int(source_info["height"]),
            settings.transform_model,
        )
        errors.extend(point_validation["errors"])
        warnings.extend(point_validation["warnings"])

    output_root = Path(settings.output_root).expanduser()
    if settings.output_root.strip():
        if not output_root.is_dir():
            errors.append(
                _tr("请选择已存在的输出根目录：{path}").format(
                    path=output_root
                )
            )

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "mode": "real_external_gcp_image_to_map",
        "input": source_info,
        "training_points": train_meta,
        "check_points": check_meta,
        "point_validation": point_validation,
        "target_crs": settings.target_crs,
        "target_crs_wkt": target_crs_wkt,
        "limitations": [
            "This mode performs external-GCP image-to-map correction.",
            "Accuracy depends on independently surveyed/reference-derived points.",
            "This mode is not SAR orbit, sensor-model or DEM terrain correction.",
            "A zero RMSE threshold means report-only and requires human acceptance.",
        ],
    }


def _write_report_markdown(report: dict[str, Any]) -> str:
    train = report["residuals"]["train"]
    check = report["residuals"]["check"]
    threshold = report["acceptance"]["threshold_pixel"]
    threshold_text = (
        _tr("`{threshold:.6g}`像素").format(threshold=threshold)
        if threshold > 0
        else _tr("未设置（仅报告，需人工判定）")
    )
    model_label = localized_model_label(report["parameters"]["model_label"])
    return (
        _tr("# 几何校正与独立精度检查报告\n\n")
        + _tr("## 结论\n\n")
        + _tr("- 运行状态：`{status}`\n").format(status=report["status"])
        + _tr("- 模型：外部训练GCP、{model_label}；\n").format(
            model_label=model_label
        )
        + _tr("- 训练GCP：{point_count}个；\n").format(
            point_count=train["point_count"]
        )
        + _tr("- 独立检查点：{point_count}个；\n").format(
            point_count=check["point_count"]
        )
        + _tr("- 训练RMSE：`{rmse_pixel:.6f}`像素 / `{rmse_m:.6f}`米；\n").format(
            rmse_pixel=train["rmse_pixel"], rmse_m=train["rmse_2d_m"]
        )
        + _tr("- 独立检查RMSE：`{rmse_pixel:.6f}`像素 / `{rmse_m:.6f}`米；\n").format(
            rmse_pixel=check["rmse_pixel"], rmse_m=check["rmse_2d_m"]
        )
        + _tr("- 独立检查最大误差：`{max_pixel:.6f}`像素 / `{max_m:.6f}`米；\n").format(
            max_pixel=check["max_error_pixel"], max_m=check["max_error_m"]
        )
        + _tr("- 用户阈值：{threshold_text}。\n\n").format(
            threshold_text=threshold_text
        )
        + _tr("## 输入\n\n")
        + _tr("- 待校正影像：`{path}`\n").format(path=report["input"]["path"])
        + _tr("- 训练GCP：`{path}`\n").format(
            path=report["control_points"]["training"]["path"]
        )
        + _tr("- 独立检查点：`{path}`\n").format(
            path=report["control_points"]["check"]["path"]
        )
        + _tr("- 目标坐标系：`{target_crs}`\n").format(
            target_crs=report["parameters"]["target_crs"]
        )
        + _tr("- 重采样：`{resampling}`\n\n").format(
            resampling=report["parameters"]["resampling"]
        )
        + _tr("## 输出\n\n")
        + _tr("- 校正GeoTIFF：`{path}`\n").format(path=report["output"]["path"])
        + _tr("- 训练残差：`03_质量检查/train_residuals.csv`\n")
        + _tr("- 检查点残差：`03_质量检查/check_residuals.csv`\n\n")
        + _tr("## 科学边界\n\n")
        + _tr(
            "本结果是基于外部控制点的普通影像到地图几何校正。检查点必须与训练GCP\n"
            "互相独立，且两者都必须来自可靠外部参考。该流程不包含SAR轨道参数、\n"
            "传感器成像模型、DEM或Range-Doppler Terrain Correction，不能替代严格的\n"
            "SAR几何/地形校正。本报告仅评价基于外部GCP的影像到地图坐标校正及独立检查点精度。\n"
        )
    )


def execute_real_geometry_job(
    settings: RealGeometryJobSettings,
    *,
    run_id: str | None = None,
    progress=None,
    is_cancelled=None,
) -> RealGeometryJobResult:
    preflight = preflight_real_geometry_input(settings)
    if preflight["status"] != "PASS":
        separator = "; " if language_code() == "en" else "；"
        raise ValueError(separator.join(preflight["errors"]))
    run_id = run_id or default_real_run_id()
    run_dir = ensure_new_run_directory(Path(settings.output_root), run_id)
    point_dir = run_dir / "01_控制点"
    result_dir = run_dir / "02_校正成果"
    quality_dir = run_dir / "03_质量检查"
    report_dir = run_dir / "04_报告"
    for directory in (point_dir, result_dir, quality_dir, report_dir):
        directory.mkdir()

    status_running = run_dir / "status_running.json"
    write_json(
        status_running,
        {
            "status": "RUNNING",
            "mode": "real_external_gcp_image_to_map",
            "run_id": run_id,
            "settings": asdict(settings),
        },
    )
    try:
        if is_cancelled is not None and is_cancelled():
            raise GeometryCancelled(_tr("用户取消了 GCP 几何校正任务。"))
        if progress:
            progress(5, _tr("步骤1/5：读取外部训练GCP和独立检查点。"))
        source_path = Path(settings.source_path).expanduser().resolve()
        train, train_meta = read_control_points(
            Path(settings.training_points_path), "train"
        )
        check, check_meta = read_control_points(
            Path(settings.check_points_path), "check"
        )
        write_control_points(point_dir / "gcps_train.csv", train)
        write_control_points(point_dir / "gcps_check.csv", check)
        write_control_points(point_dir / "gcps_all.csv", [*train, *check])

        if progress:
            progress(15, _tr("步骤2/5：拟合外部训练GCP变换模型。"))
        fit = fit_transform_model(train, settings.transform_model)
        output_path = result_dir / f"{source_path.stem}_georeferenced.tif"
        output_info = georeference_with_external_gcps(
            source_path,
            output_path,
            train,
            settings.target_crs,
            resampling=settings.resampling,
            x_resolution=settings.x_resolution,
            y_resolution=settings.y_resolution,
            run_id=run_id,
            transform_model=settings.transform_model,
            progress=(
                (lambda value, message: progress(20 + int(value * 0.55), message))
                if progress
                else None
            ),
            is_cancelled=is_cancelled,
        )

        if progress:
            progress(78, _tr("步骤3/5：计算训练残差和独立检查点RMSE。"))
        target_srs = spatial_reference(settings.target_crs)
        train_rows, train_metrics = calculate_residuals(
            train,
            fit,
            target_srs,
            output_info["geotransform"],
        )
        check_rows, check_metrics = calculate_residuals(
            check,
            fit,
            target_srs,
            output_info["geotransform"],
        )
        write_rows(quality_dir / "train_residuals.csv", train_rows)
        write_rows(quality_dir / "check_residuals.csv", check_rows)
        preview_path = quality_dir / "geometry_correction_qa_preview.png"
        render_real_geometry_preview(
            source_path,
            output_path,
            train,
            check,
            train_rows,
            check_rows,
            preview_path,
            str(fit["label"]),
        )

        threshold = settings.check_rmse_threshold_pixel
        threshold_applied = threshold > 0.0
        threshold_pass = (
            check_metrics["rmse_pixel"] <= threshold
            if threshold_applied
            else None
        )
        status = (
            "PASS"
            if threshold_applied and threshold_pass
            else "FAIL_ACCURACY_THRESHOLD"
            if threshold_applied
            else "COMPLETED_REQUIRES_HUMAN_ACCURACY_REVIEW"
        )

        if progress:
            progress(88, _tr("步骤4/5：写入质量检查报告。"))
        report = {
            "schema_version": "real-geometry-correction-v2",
            "status": status,
            "run_id": run_id,
            "mode": "real_external_gcp_image_to_map",
            "input": inspect_raster(source_path),
            "control_points": {
                "training": train_meta,
                "check": check_meta,
            },
            "parameters": {
                "target_crs": settings.target_crs,
                "model": settings.transform_model,
                "model_label": fit["label"],
                "resampling": settings.resampling,
                "x_resolution": settings.x_resolution,
                "y_resolution": settings.y_resolution,
            },
            "fit": {
                key: value
                for key, value in fit.items()
                if key not in {"coefficients", "control_pixels", "pixel_centre", "pixel_scale"}
            },
            "residuals": {
                "train": train_metrics,
                "check": check_metrics,
            },
            "acceptance": {
                "threshold_pixel": threshold,
                "threshold_applied": threshold_applied,
                "threshold_pass": threshold_pass,
                "requires_human_review": not threshold_applied,
            },
            "output": output_info,
            "qa_preview": str(preview_path),
            "scientific_boundary": {
                "ordinary_image_to_map_gcp_correction": True,
                "sar_orbit_sensor_model": False,
                "dem_terrain_correction": False,
                "formal_teacher_data_validation_pending": True,
            },
        }
        report_json = report_dir / "geometry_correction_report.json"
        write_json(report_json, report)
        (report_dir / "geometry_correction_report.md").write_text(
            _write_report_markdown(report),
            encoding="utf-8",
        )
        (run_dir / "成果说明.txt").write_text(
            _tr("02_校正成果：校正后的GeoTIFF\n")
            + _tr("03_质量检查：训练点与独立检查点残差\n")
            + _tr("04_报告：JSON和Markdown质量报告\n")
            + _tr("注意：本模式不是SAR轨道/DEM地形校正。\n"),
            encoding="utf-8",
        )
        status_running.unlink(missing_ok=True)
        write_json(
            run_dir / "status_complete.json",
            {
                "status": status,
                "run_id": run_id,
                "output": str(output_path),
                "check_rmse_pixel": check_metrics["rmse_pixel"],
                "check_rmse_m": check_metrics["rmse_2d_m"],
            },
        )
        if progress:
            progress(
                100,
                _tr("步骤5/5：GCP 几何校正任务完成，等待人工精度判定。"),
            )
        return RealGeometryJobResult(
            run_dir=run_dir,
            output_path=output_path,
            report_path=report_json,
            status=status,
            train_rmse_pixel=float(train_metrics["rmse_pixel"]),
            check_rmse_pixel=float(check_metrics["rmse_pixel"]),
            check_max_error_pixel=float(check_metrics["max_error_pixel"]),
        )
    except GeometryCancelled:
        status_running.unlink(missing_ok=True)
        write_json(
            run_dir / "status_cancelled.json",
            {"status": "CANCELLED", "run_id": run_id},
        )
        raise
    except Exception as exc:
        status_running.unlink(missing_ok=True)
        write_json(
            run_dir / "status_failed.json",
            {
                "status": "FAILED",
                "run_id": run_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise
