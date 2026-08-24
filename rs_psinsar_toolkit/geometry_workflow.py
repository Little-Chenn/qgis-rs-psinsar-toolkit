"""M5.1 non-destructive geometry-correction teaching workflow."""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .geometry_core import (
    PIXEL_CONVENTION,
    PURPOSE,
    VERSION,
    GeometryCancelled,
    calculate_residuals,
    compare_rasters,
    environment_manifest,
    export_unreferenced_png,
    fit_affine,
    generate_control_points,
    georeference_png,
    geotransform_differences,
    render_markdown_report,
    sha256_file,
    validate_reference_raster,
    write_control_points,
    write_rows,
)
from .localization import language_code, tr
from .tasking import RunContext, RunStatus, TaskSpec


ProgressCallback = Callable[[int, str], None] | None
CancelCallback = Callable[[], bool] | None
ALLOWED_RESAMPLING = {"near", "bilinear", "cubic"}
RUN_INFO_DIR = "00_运行记录"
CONTROL_POINT_DIR = "01_控制点"
INTERMEDIATE_DIR = "02_中间文件"
RESULT_DIR = "03_校正成果"
QUALITY_DIR = "04_精度质检"
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


@dataclass(frozen=True)
class GeometryJobSettings:
    source_path: str
    output_root: str
    resampling: str = "bilinear"
    acknowledge_teaching_mode: bool = False


@dataclass(frozen=True)
class GeometryJobResult:
    run_dir: Path
    report_path: Path
    artifacts: dict[str, str]
    check_rmse_pixel: float
    check_max_error_pixel: float


def _write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")


def _write_text_exclusive(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def _sidecar_manifest(source: Path) -> list[dict[str, Any]]:
    candidates = [
        Path(f"{source}.aux.xml"),
        source.with_suffix(".tfw"),
        source.with_suffix(".wld"),
    ]
    records = []
    for path in candidates:
        if path.is_file():
            records.append(
                {
                    "path": str(path.resolve()),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return records


def validate_geometry_settings(
    settings: GeometryJobSettings,
) -> tuple[list[str], dict[str, Any] | None]:
    """Validate user choices without creating files."""
    errors: list[str] = []
    source = Path(settings.source_path).expanduser()
    output_root = Path(settings.output_root).expanduser()

    if not settings.source_path.strip():
        errors.append(_tr("请选择参考GeoTIFF。"))
    elif source.suffix.lower() not in {".tif", ".tiff"}:
        errors.append(_tr("参考影像必须是.tif或.tiff文件。"))
    elif not source.is_file():
        errors.append(_tr("参考GeoTIFF不存在。"))

    if not settings.output_root.strip():
        errors.append(_tr("请选择已有的输出根目录。"))
    elif not output_root.is_dir():
        errors.append(_tr("输出根目录不存在或不是文件夹。"))

    if settings.resampling not in ALLOWED_RESAMPLING:
        errors.append(_tr("重采样方法必须是near、bilinear或cubic。"))

    if not settings.acknowledge_teaching_mode:
        errors.append(_tr("请确认已了解本功能仅用于几何校正流程验证。"))

    info = None
    if not errors:
        try:
            info = validate_reference_raster(source.resolve())
        except Exception as exc:
            errors.append(_tr("参考影像预检失败：{error}").format(error=exc))
    return errors, info


def preflight_geometry_input(
    settings: GeometryJobSettings,
) -> dict[str, Any]:
    errors, info = validate_geometry_settings(settings)
    if errors:
        return {"status": "REJECTED", "errors": errors, "input": info}
    assert info is not None
    return {
        "status": "PASS",
        "errors": [],
        "input": info,
        "method": {
            "mode": "teaching_reference_geotransform",
            "model": "first-order affine",
            "grid": "5x5 checkerboard train/check split",
            "metric_crs": "EPSG:32650",
            "resampling": settings.resampling,
        },
        "limitations": [
            "GCP map coordinates are generated from the source GeoTransform.",
            "Near-zero RMSE validates reproducibility, not manual GCP accuracy.",
            "The M5.1.1 mode requires single-band Byte EPSG:4326 input.",
            "This output does not replace original quantitative SAR data.",
        ],
    }


def _check_cancelled(is_cancelled: CancelCallback) -> None:
    if is_cancelled is not None and is_cancelled():
        raise GeometryCancelled(_tr("用户取消了几何校正任务。"))


def _emit(
    progress: ProgressCallback,
    value: int,
    message: str,
) -> None:
    if progress is not None:
        progress(max(0, min(100, int(value))), message)


def _scaled_progress(
    progress: ProgressCallback,
    start: int,
    end: int,
) -> Callable[[int, str], None]:
    def callback(value: int, message: str) -> None:
        scaled = start + int((end - start) * value / 100)
        _emit(progress, scaled, message)

    return callback


def default_run_id() -> str:
    return (
        datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
        + "_geometry_teaching"
    )


def _render_user_readme(
    *,
    run_id: str,
    source: Path,
    restored_name: str,
    check_metrics: dict[str, Any],
    source_hash: str,
) -> str:
    template = _tr("""# 几何校正流程验证成果说明

运行状态：`PASS`  
运行ID：`{run_id}`  
源影像：`{source}`  
源影像SHA-256：`{source_hash}`

## 首先查看

- 最终校正GeoTIFF：`{result_dir}/{restored_name}`
- 图像对比与差异检查：`{quality_dir}/comparison_preview.png`
- 精度报告：`{quality_dir}/geometry_correction_report.md`

## 精度摘要

- 训练GCP：13个；
- 独立检查点：12个；
- 独立检查二维RMSE：`{check_rmse_m:.9f} m`；
- 独立检查像素RMSE：`{check_rmse_pixel:.12g} pixel`；
- 独立检查最大误差：`{check_max_pixel:.12g} pixel`。

## 文件夹含义

- `{run_info_dir}`：输入清单、参数、运行状态和机器可读结果；
- `{control_point_dir}`：全部控制点、训练点和独立检查点CSV；
- `{intermediate_dir}`：去除空间参考的教学中间PNG；
- `{result_dir}`：最终恢复空间参考的GeoTIFF；
- `{quality_dir}`：训练/检查残差、对比图和完整质量报告。

## 重要限制

本模式的GCP地图坐标由源GeoTIFF原有GeoTransform自动生成。近零RMSE
只证明软件流程、训练/检查拆分和像元坐标约定可复现，不能代表真实
人工选点或外部控制点条件下的配准精度。Byte PNG和恢复GeoTIFF不
替代原始浮点SAR定量数据。
""")
    return template.format(
        run_id=run_id,
        source=source,
        source_hash=source_hash,
        result_dir=RESULT_DIR,
        restored_name=restored_name,
        quality_dir=QUALITY_DIR,
        check_rmse_m=check_metrics["rmse_2d_m"],
        check_rmse_pixel=check_metrics["rmse_pixel"],
        check_max_pixel=check_metrics["max_error_pixel"],
        run_info_dir=RUN_INFO_DIR,
        control_point_dir=CONTROL_POINT_DIR,
        intermediate_dir=INTERMEDIATE_DIR,
    )


def execute_geometry_job(
    settings: GeometryJobSettings,
    *,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
    run_id: str | None = None,
) -> GeometryJobResult:
    """Execute a new teaching-mode run and never overwrite an existing run."""
    preflight = preflight_geometry_input(settings)
    if preflight["status"] != "PASS":
        separator = "; " if language_code() == "en" else "；"
        raise ValueError(separator.join(preflight["errors"]))

    source = Path(settings.source_path).expanduser().resolve()
    output_root = Path(settings.output_root).expanduser().resolve()
    source_info = preflight["input"]
    sidecars_before = _sidecar_manifest(source)
    spec = TaskSpec(
        module_id="geometry_teaching",
        module_version=VERSION,
        inputs={
            "source": source_info,
            "sidecars": sidecars_before,
        },
        parameters={
            "mode": "teaching_reference_geotransform",
            "resampling": settings.resampling,
            "pixel_convention": PIXEL_CONVENTION,
            "metric_crs": "EPSG:32650",
        },
    )
    context = RunContext.create(
        output_root,
        spec,
        run_id=run_id or default_run_id(),
        metadata_subdir=RUN_INFO_DIR,
    )
    context.mark_running()
    run_dir = context.run_dir
    run_info_dir = context.metadata_dir
    control_point_dir = run_dir / CONTROL_POINT_DIR
    intermediate_dir = run_dir / INTERMEDIATE_DIR
    result_dir = run_dir / RESULT_DIR
    quality_dir = run_dir / QUALITY_DIR
    try:
        for directory in (
            control_point_dir,
            intermediate_dir,
            result_dir,
            quality_dir,
        ):
            directory.mkdir(exist_ok=False)
    except Exception as exc:
        context.mark_failed(exc)
        raise
    stem = source.stem
    png_path = intermediate_dir / f"{stem}_unreferenced.png"
    restored_path = result_dir / f"{stem}_georeferenced.tif"
    comparison_path = quality_dir / "comparison_preview.png"
    report_json = quality_dir / "geometry_correction_report.json"
    report_md = quality_dir / "geometry_correction_report.md"
    user_readme = run_dir / "成果说明.md"

    try:
        _emit(progress, 2, _tr("输入预检已通过，正在记录manifest……"))
        _check_cancelled(is_cancelled)
        _write_json_exclusive(
            run_info_dir / "input_manifest.json",
            {
                "purpose": PURPOSE,
                "script_version": VERSION,
                "input": source_info,
                "input_sidecars": sidecars_before,
                "environment": environment_manifest(),
                "pixel_convention": PIXEL_CONVENTION,
                "scientific_limitations": preflight["limitations"],
                "output_policy": "new run directory; refuse overwrite",
            },
        )

        _emit(progress, 5, _tr("步骤1/6：导出无地理信息PNG。"))
        png_info = export_unreferenced_png(
            source,
            png_path,
            progress=_scaled_progress(progress, 5, 22),
            is_cancelled=is_cancelled,
        )

        _emit(progress, 24, _tr("步骤2/6：生成训练点和独立检查点。"))
        _check_cancelled(is_cancelled)
        points = generate_control_points(
            int(source_info["width"]),
            int(source_info["height"]),
            source_info["geotransform"],
        )
        training = [point for point in points if point.subset == "train"]
        checks = [point for point in points if point.subset == "check"]
        write_control_points(control_point_dir / "gcps_all.csv", points)
        write_control_points(control_point_dir / "gcps_train.csv", training)
        write_control_points(control_point_dir / "gcps_check.csv", checks)

        _emit(progress, 31, _tr("步骤3/6：仅用训练点拟合一阶仿射模型。"))
        _check_cancelled(is_cancelled)
        fit = fit_affine(training)
        coefficients = np.asarray(
            fit.pop("coefficients"),
            dtype=np.float64,
        )
        train_rows, train_metrics = calculate_residuals(
            training,
            coefficients,
            source_info["geotransform"],
        )
        check_rows, check_metrics = calculate_residuals(
            checks,
            coefficients,
            source_info["geotransform"],
        )
        write_rows(quality_dir / "train_residuals.csv", train_rows)
        write_rows(quality_dir / "check_residuals.csv", check_rows)

        _emit(progress, 39, _tr("步骤4/6：使用训练GCP恢复GeoTIFF。"))
        output_info = georeference_png(
            png_path,
            restored_path,
            training,
            source_info,
            context.run_dir.name,
            resampling=settings.resampling,
            progress=_scaled_progress(progress, 39, 70),
            is_cancelled=is_cancelled,
        )

        _emit(progress, 72, _tr("步骤5/6：计算网格、像元值和叠加比较。"))
        _check_cancelled(is_cancelled)
        geotransform_comparison = geotransform_differences(
            source_info["geotransform"],
            output_info["geotransform"],
        )
        raster_comparison = compare_rasters(
            source,
            restored_path,
            comparison_path,
            progress=_scaled_progress(progress, 72, 91),
            is_cancelled=is_cancelled,
        )

        _emit(progress, 93, _tr("步骤6/6：验证源文件完整性并生成报告。"))
        _check_cancelled(is_cancelled)
        source_hash_after = sha256_file(source)
        sidecars_after = _sidecar_manifest(source)
        source_unchanged = source_hash_after == source_info["sha256"]
        sidecars_unchanged = sidecars_after == sidecars_before
        acceptance = {
            "check_rmse_pixel_max": 0.25,
            "check_max_error_pixel_max": 0.5,
            "check_rmse_pixel_pass": check_metrics["rmse_pixel"] <= 0.25,
            "check_max_error_pixel_pass": (
                check_metrics["max_error_pixel"] <= 0.5
            ),
            "source_integrity_pass": (
                source_unchanged and sidecars_unchanged
            ),
            "png_has_no_spatial_reference_pass": (
                not png_info["projection_wkt"]
                and png_info["geotransform"] is None
                and png_info["gcp_count"] == 0
            ),
            "comparison_layout_alignment_pass": bool(
                raster_comparison["right_column_alignment_pass"]
            ),
        }
        status = (
            "PASS"
            if all(
                value
                for key, value in acceptance.items()
                if key.endswith("_pass")
            )
            else "FAIL"
        )
        report = {
            "status": status,
            "purpose": PURPOSE,
            "run_id": context.run_dir.name,
            "script_version": VERSION,
            "pixel_convention": PIXEL_CONVENTION,
            "input": source_info,
            "unreferenced_png": png_info,
            "control_points": {
                "all": len(points),
                "train": len(training),
                "check": len(checks),
                "split": "5x5 grid, checkerboard train/check split",
            },
            "method": {
                "mode": "teaching_reference_geotransform",
                "model": "first-order 2D affine polynomial",
                "resampling": settings.resampling,
                "metric_crs": "EPSG:32650",
                "fit": fit,
                "coefficients": coefficients.tolist(),
                "fit_uses": "training points only",
                "output_grid": (
                    "explicitly matched to reference CRS, bounds, "
                    "width and height"
                ),
            },
            "residuals": {
                "train": train_metrics,
                "check": check_metrics,
            },
            "output": output_info,
            "geotransform_comparison": geotransform_comparison,
            "raster_comparison": raster_comparison,
            "source_integrity": {
                "before": source_info["sha256"],
                "after": source_hash_after,
                "unchanged": source_unchanged,
                "sidecars_before": sidecars_before,
                "sidecars_after": sidecars_after,
                "sidecars_unchanged": sidecars_unchanged,
            },
            "acceptance": acceptance,
            "output_structure": {
                "user_readme": str(user_readme),
                "run_info": str(run_info_dir),
                "control_points": str(control_point_dir),
                "intermediate": str(intermediate_dir),
                "result": str(result_dir),
                "quality": str(quality_dir),
            },
            "scientific_limitations": preflight["limitations"],
            "ps_insar_semantics": {
                "applicability": "not used by geometry workflow",
                "velocity_unit": "mm/year",
                "displacement_unit": "mm",
                "positive_direction": "vertical upward",
                "negative_direction": "vertical downward",
            },
        }
        _write_json_exclusive(report_json, report)
        _write_text_exclusive(report_md, render_markdown_report(report))
        if status != "PASS":
            raise RuntimeError(_tr("一个或多个几何校正验收门未通过。"))
        _write_text_exclusive(
            user_readme,
            _render_user_readme(
                run_id=context.run_dir.name,
                source=source,
                restored_name=restored_path.name,
                check_metrics=check_metrics,
                source_hash=source_info["sha256"],
            ),
        )

        artifacts = {
            "user_readme": str(user_readme),
            "unreferenced_png": str(png_path),
            "restored_geotiff": str(restored_path),
            "gcp_all": str(control_point_dir / "gcps_all.csv"),
            "gcp_train": str(control_point_dir / "gcps_train.csv"),
            "gcp_check": str(control_point_dir / "gcps_check.csv"),
            "train_residuals": str(quality_dir / "train_residuals.csv"),
            "check_residuals": str(quality_dir / "check_residuals.csv"),
            "comparison_preview": str(comparison_path),
            "report_json": str(report_json),
            "report_md": str(report_md),
        }
        context.mark_pass(
            {
                "status": "PASS",
                "artifacts": artifacts,
                "check_rmse_pixel": check_metrics["rmse_pixel"],
                "check_max_error_pixel": check_metrics["max_error_pixel"],
            }
        )
        _emit(progress, 100, _tr("几何校正教学任务完成。"))
        return GeometryJobResult(
            run_dir=run_dir,
            report_path=report_json,
            artifacts=artifacts,
            check_rmse_pixel=float(check_metrics["rmse_pixel"]),
            check_max_error_pixel=float(check_metrics["max_error_pixel"]),
        )
    except GeometryCancelled as exc:
        if context.status == RunStatus.RUNNING:
            context.mark_cancelled(str(exc))
        raise
    except Exception as exc:
        if context.status == RunStatus.RUNNING:
            try:
                _write_json_exclusive(
                    run_info_dir / "geometry_failure_detail.json",
                    {
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "source_sha256_after_failure": (
                            sha256_file(source) if source.is_file() else None
                        ),
                    },
                )
            finally:
                context.mark_failed(exc)
        raise
