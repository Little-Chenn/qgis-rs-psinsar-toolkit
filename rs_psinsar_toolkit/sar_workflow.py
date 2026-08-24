"""M8.4 non-overwriting SAR mosaic, clip and dB workflow."""

from __future__ import annotations

import json
import math
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .sar_core import (
    COLOR_MODES,
    COLOR_RAMPS,
    DISPLAY_METHODS,
    NODATA_DEFAULT,
    VERSION,
    SarCancelled,
    clip_mosaic,
    create_display_product,
    estimate_float32_grid,
    grids_equal,
    inspect_inputs,
    linear_power_to_db,
    mosaic_to_common_grid,
    rectangles_intersect,
    sampled_percentiles,
    sampled_display_statistics,
    sha256_file,
    validate_mask,
)
from .localization import language_code, tr
from .tasking import RunContext, RunStatus, TaskSpec


ProgressCallback = Callable[[int, str], None] | None
CancelCallback = Callable[[], bool] | None
RESAMPLING_METHODS = {"near", "bilinear", "cubic"}
RUN_INFO_DIR = "00_运行记录"
MOSAIC_DIR = "01_线性镶嵌"
CLIP_DIR = "02_线性裁剪"
DB_DIR = "03_dB成果"
QUALITY_DIR = "04_质量报告"
DISPLAY_DIR = "05_显示产品"
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


@dataclass(frozen=True)
class SarJobSettings:
    raster_paths: tuple[str, ...]
    mask_path: str
    output_root: str
    x_resolution: float = 0.0
    y_resolution: float = 0.0
    mosaic_resampling: str = "near"
    clip_resampling: str = "near"
    output_nodata: float = NODATA_DEFAULT
    stretch_low: float = 2.0
    stretch_high: float = 98.0
    display_method: str = "percentile"
    brightness: int = 0
    contrast: int = 0
    gamma: float = 1.0
    color_mode: str = "grayscale"
    color_ramp: str = "viridis"
    create_display_product: bool = True
    feather_pixels: int = 0
    acknowledge_linear_power: bool = False
    acknowledge_source_order: bool = False
    acknowledge_mixed_orbits: bool = False
    acknowledge_radiometric_warnings: bool = False
    acknowledge_cubic_resampling: bool = False


@dataclass(frozen=True)
class SarJobResult:
    run_dir: Path
    report_path: Path
    artifacts: dict[str, str]
    display_min: float
    display_max: float


def _write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")


def _write_text_exclusive(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


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
        _emit(
            progress,
            start + int((end - start) * value / 100),
            message,
        )

    return callback


def _check_cancelled(is_cancelled: CancelCallback) -> None:
    if is_cancelled is not None and is_cancelled():
        raise SarCancelled(_tr("用户取消了SAR处理任务。"))


def validate_sar_settings(settings: SarJobSettings) -> list[str]:
    errors: list[str] = []
    if len(settings.raster_paths) < 1:
        errors.append(_tr("请至少选择一幅SAR GeoTIFF。"))
    resolved = []
    for value in settings.raster_paths:
        path = Path(value).expanduser()
        if path.suffix.lower() not in {".tif", ".tiff"}:
            errors.append(_tr("输入不是GeoTIFF：{path}").format(path=value))
        elif not path.is_file():
            errors.append(_tr("输入影像不存在：{path}").format(path=value))
        else:
            resolved.append(path.resolve())
    if len(set(resolved)) != len(resolved):
        errors.append(_tr("输入影像列表包含重复路径。"))

    mask = Path(settings.mask_path).expanduser()
    if not settings.mask_path.strip():
        errors.append(_tr("请选择Polygon或MultiPolygon裁剪面。"))
    elif mask.suffix.lower() not in {".gpkg", ".shp", ".geojson"}:
        errors.append(_tr("裁剪面应为GPKG、SHP或GeoJSON。"))
    elif not mask.is_file():
        errors.append(_tr("裁剪面不存在。"))

    output_root = Path(settings.output_root).expanduser()
    if not settings.output_root.strip():
        errors.append(_tr("请选择已有输出根目录。"))
    elif not output_root.is_dir():
        errors.append(_tr("输出根目录不存在或不是文件夹。"))

    for label, value in (
        (_tr("X分辨率"), settings.x_resolution),
        (_tr("Y分辨率"), settings.y_resolution),
    ):
        if not math.isfinite(value) or value < 0:
            errors.append(
                _tr("{label}必须为0（自动）或正数。").format(label=label)
            )
    if settings.mosaic_resampling not in RESAMPLING_METHODS:
        errors.append(_tr("无法识别镶嵌重采样方法。"))
    if settings.clip_resampling not in RESAMPLING_METHODS:
        errors.append(_tr("无法识别裁剪重采样方法。"))
    if (
        "cubic" in {
            settings.mosaic_resampling,
            settings.clip_resampling,
        }
        and not settings.acknowledge_cubic_resampling
    ):
        errors.append(
            _tr(
                "三次卷积可能使非负线性功率产生非物理负值。"
                "建议改用最近邻；如确需使用，请勾选风险确认。"
            )
        )
    if not math.isfinite(settings.output_nodata):
        errors.append(_tr("输出NoData必须是有限数值。"))
    if not (
        0 <= settings.stretch_low < settings.stretch_high <= 100
    ):
        errors.append(_tr("显示分位数必须满足0≤低值<高值≤100。"))
    if settings.display_method not in DISPLAY_METHODS:
        errors.append(_tr("无法识别显示增强方法。"))
    if settings.color_mode not in COLOR_MODES:
        errors.append(_tr("无法识别颜色模式。"))
    if settings.color_ramp not in COLOR_RAMPS:
        errors.append(_tr("无法识别单波段伪彩色色带。"))
    if not -100 <= settings.brightness <= 100:
        errors.append(_tr("亮度必须在-100—100之间。"))
    if not -99 <= settings.contrast <= 99:
        errors.append(_tr("对比度必须在-99—99之间。"))
    if not math.isfinite(settings.gamma) or settings.gamma <= 0.0:
        errors.append(_tr("Gamma必须为正数。"))
    if not 0 <= settings.feather_pixels <= 1000:
        errors.append(_tr("基础外缘羽化距离必须为0—1000像素。"))
    if not settings.acknowledge_linear_power:
        errors.append(
            _tr("请确认输入为线性功率值并同意执行10log10转换。")
        )
    if len(settings.raster_paths) > 1 and not settings.acknowledge_source_order:
        errors.append(
            _tr("请确认输入顺序规则：后输入有效像元覆盖先输入有效像元。")
        )
    return errors


def preflight_sar_job(
    settings: SarJobSettings,
    *,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
) -> dict[str, Any]:
    errors = validate_sar_settings(settings)
    if errors:
        return {"status": "REJECTED", "errors": errors}
    paths = tuple(
        Path(value).expanduser().resolve()
        for value in settings.raster_paths
    )
    try:
        inspection = inspect_inputs(
            paths,
            progress=progress,
            is_cancelled=is_cancelled,
        )
        mask = validate_mask(
            settings.mask_path,
            inspection["projection_wkt"],
        )
        if not rectangles_intersect(
            inspection["union_bounds"],
            mask["bounds"],
        ):
            raster_bounds = inspection["union_bounds"]
            mask_bounds = mask["bounds"]
            raise ValueError(
                _tr(
                    "裁剪面与输入影像联合范围不相交。影像范围 "
                    "[{raster_xmin:.6f}, {raster_ymin:.6f}, {raster_xmax:.6f}, {raster_ymax:.6f}]；"
                    "裁剪面范围 [{mask_xmin:.6f}, {mask_ymin:.6f}, {mask_xmax:.6f}, {mask_ymax:.6f}]。"
                    "请改选空间相交的单景或裁剪面。"
                ).format(
                    raster_xmin=raster_bounds["xmin"],
                    raster_ymin=raster_bounds["ymin"],
                    raster_xmax=raster_bounds["xmax"],
                    raster_ymax=raster_bounds["ymax"],
                    mask_xmin=mask_bounds["xmin"],
                    mask_ymin=mask_bounds["ymin"],
                    mask_xmax=mask_bounds["xmax"],
                    mask_ymax=mask_bounds["ymax"],
                )
            )
        assessment = inspection["scientific_assessment"]
        if assessment["errors"]:
            separator = "; " if language_code() == "en" else "；"
            raise ValueError(separator.join(assessment["errors"]))
        if (
            assessment["mixed_orbit_directions"]
            and not settings.acknowledge_mixed_orbits
        ):
            raise ValueError(
                _tr(
                    "检测到升轨/降轨混合。建议分组处理；如确需混合，"
                    "请勾选科学风险确认。"
                )
            )
        if (
            assessment["radiometric_warning"]
            and not settings.acknowledge_radiometric_warnings
        ):
            raise ValueError(
                _tr(
                    "检测到超过6 dB的组间中位强度异常。插件不会自动归一化；"
                    "请检查报告并勾选风险确认。"
                )
            )
        x_resolution = (
            settings.x_resolution
            if settings.x_resolution > 0
            else float(inspection["first_x_resolution"])
        )
        y_resolution = (
            settings.y_resolution
            if settings.y_resolution > 0
            else float(inspection["first_y_resolution"])
        )
        if x_resolution <= 0 or y_resolution <= 0:
            raise ValueError(_tr("目标分辨率无效。"))
        processing_bounds = {
            "xmin": max(
                inspection["union_bounds"]["xmin"], mask["bounds"]["xmin"]
            ),
            "ymin": max(
                inspection["union_bounds"]["ymin"], mask["bounds"]["ymin"]
            ),
            "xmax": min(
                inspection["union_bounds"]["xmax"], mask["bounds"]["xmax"]
            ),
            "ymax": min(
                inspection["union_bounds"]["ymax"], mask["bounds"]["ymax"]
            ),
        }
        union_estimate = estimate_float32_grid(
            inspection["union_bounds"], x_resolution, y_resolution
        )
        processing_estimate = estimate_float32_grid(
            processing_bounds, x_resolution, y_resolution
        )
        warnings = list(assessment["warnings"])
        if "cubic" in {
            settings.mosaic_resampling,
            settings.clip_resampling,
        }:
            warnings.append(
                _tr(
                    "已确认使用三次卷积；质量报告将精确记录因此产生或"
                    "保留下来的负线性功率像元。"
                )
            )
    except SarCancelled:
        raise
    except Exception as exc:
        return {"status": "REJECTED", "errors": [str(exc)]}
    return {
        "status": "PASS",
        "errors": [],
        "inspection": inspection,
        "mask": mask,
        "resolved_parameters": {
            "x_resolution": x_resolution,
            "y_resolution": y_resolution,
            "target_crs": inspection["crs"],
            "mosaic_resampling": settings.mosaic_resampling,
            "clip_resampling": settings.clip_resampling,
            "output_nodata": settings.output_nodata,
            "stretch_low": settings.stretch_low,
            "stretch_high": settings.stretch_high,
            "display_method": settings.display_method,
            "brightness": settings.brightness,
            "contrast": settings.contrast,
            "gamma": settings.gamma,
            "color_mode": settings.color_mode,
            "color_ramp": settings.color_ramp,
            "create_display_product": settings.create_display_product,
            "feather_pixels": settings.feather_pixels,
            "processing_bounds": processing_bounds,
            "union_grid_estimate": union_estimate,
            "mask_limited_grid_estimate": processing_estimate,
            "db_value_semantics": assessment["recommended_db_label"],
            "nan_safe_vrt": True,
            "source_count": len(paths),
            "cubic_resampling_acknowledged": (
                settings.acknowledge_cubic_resampling
            ),
        },
        "warnings": warnings,
        "limitations": [
            "当前流程要求所有源栅格和裁剪面使用同一CRS。",
            "Inputs must be single-band non-negative linear-power rasters.",
            "Single-scene clip-and-dB runs are supported.",
            "Later valid source pixels overwrite earlier valid source pixels.",
            "NaN is treated as source NoData through temporary in-memory VRTs.",
            "The mosaic grid is limited to the mask-envelope intersection.",
            "No automatic seamline or physical radiometric balancing is applied.",
            "Display enhancement never changes the Float32 scientific raster.",
            "Optional feathering affects only the 8-bit display product outer edge.",
            "Cubic resampling can create negative power and requires explicit acknowledgement.",
            "当前处理阶段不生成最终专题图。",
        ],
    }


def default_run_id() -> str:
    return (
        datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
        + "_sar_mosaic_clip_db"
    )


def _hash_inputs(
    paths: list[Path],
    *,
    progress: ProgressCallback,
    is_cancelled: CancelCallback,
    start: int,
    end: int,
) -> dict[str, str]:
    values = {}
    count = len(paths)
    for index, path in enumerate(paths):
        item_start = start + int((end - start) * index / count)
        item_end = start + int((end - start) * (index + 1) / count)
        values[str(path)] = sha256_file(
            path,
            progress=progress,
            is_cancelled=is_cancelled,
            progress_start=item_start,
            progress_end=item_end,
        )
    return values


def _mask_source_files(mask_path: Path) -> list[Path]:
    """Return every physical file that belongs to a supported mask dataset."""
    if mask_path.suffix.lower() != ".shp":
        return [mask_path]
    components = []
    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        candidate = mask_path.with_suffix(suffix)
        if candidate.is_file():
            components.append(candidate)
    return components


def _render_user_readme(
    *,
    run_id: str,
    input_count: int,
    display_min: float,
    display_max: float,
    settings: SarJobSettings,
) -> str:
    display_product = (
        _tr("- 8位显示产品：`{display_dir}/sar_display_rgba_8bit.tif`\n").format(
            display_dir=DISPLAY_DIR
        )
        if settings.create_display_product
        else _tr("- 本次未生成可选8位显示产品。\n")
    )
    template = _tr("""# SAR 影像镶嵌、裁剪与显示增强成果说明

运行状态：`PASS`  
运行ID：`{run_id}`  
输入影像：{input_count}幅（顺序见 `{run_info_dir}/input_manifest.json`）

## 首先查看

- 最终dB栅格：`{db_dir}/sar_mosaic_clip_db.tif`
- 线性裁剪结果：`{clip_dir}/sar_mosaic_clip_linear.tif`
- 处理与质量报告：`{quality_dir}/sar_processing_report.md`
{display_product}

## 显示建议

- 单位：dB；
- 公式：`10*log10(linear_power)`；
- 显示方法：`{display_method}`；
- 显示范围：
  `{display_min:.6f} — {display_max:.6f} dB`；
- 该范围只用于显示，不改变栅格像元值。

## 文件夹含义

- `{run_info_dir}`：输入顺序、哈希、参数和任务状态；
- `{mosaic_dir}`：统一网格后的线性功率镶嵌；
- `{clip_dir}`：按矢量掩膜得到的线性功率裁剪结果；
- `{db_dir}`：最终Float32 dB栅格；
- `{quality_dir}`：处理报告和质量检查。
- `{display_dir}`：可选RGBA 8位显示产品，仅用于可视化。

## 重要规则

输入顺序具有科学含义：后输入影像的有效像元覆盖先输入影像的有效
像元；未声明NoData的NaN边缘由临时只读VRT保护，不覆盖已有有效值。
本版本不做自动seamline或物理辐射平衡。基础外缘羽化仅作用于8位
显示产品，不改变Float32线性功率或dB成果，也不表示自动无缝拼接。
""")
    return template.format(
        run_id=run_id,
        input_count=input_count,
        run_info_dir=RUN_INFO_DIR,
        db_dir=DB_DIR,
        clip_dir=CLIP_DIR,
        quality_dir=QUALITY_DIR,
        display_product=display_product,
        display_method=settings.display_method,
        display_min=display_min,
        display_max=display_max,
        mosaic_dir=MOSAIC_DIR,
        display_dir=DISPLAY_DIR,
    )


def _render_markdown_report(report: dict[str, Any]) -> str:
    parameters = report["parameters"]
    warning_lines = report.get("scientific_warnings") or []
    warning_text = (
        "\n".join(f"- {item}" for item in warning_lines)
        if warning_lines
        else _tr("- 未发现需要人工确认的科学一致性警告。")
    )
    template = _tr("""# ORG真实数据SAR处理报告

状态：`{status}`  
运行ID：`{run_id}`  
输入数量：{raster_count}  
CRS：`{crs}`

## 处理链

```text
显式输入顺序
→ {x_resolution} × {y_resolution} 目标网格镶嵌
→ Polygon裁剪
→ 10*log10(linear_power)
→ {display_method}显示增强
```

后输入有效像元覆盖先输入有效像元；不做自动seamline或物理辐射平衡。

## 真实产品科学预检

{warning_text}

- dB语义：`{db_value_semantics}`
- NaN安全VRT：`{nan_safe_vrt}`
- 掩膜范围预计三阶段未压缩空间：`{estimated_gib:.3f} GiB`

## 输出

- 线性镶嵌：`{mosaic_linear}`
- 线性裁剪：`{clip_linear}`
- dB栅格：`{db_raster}`
- 8位显示产品：`{display_raster}`
- 显示范围：`{display_minimum:.6f}` 至
  `{display_maximum:.6f} dB`

## 质量门

- 裁剪与dB网格一致：`{clip_db_grid_equal}`
- 输入完整性：`{source_integrity_pass}`
- dB有效像元数：`{valid_pixel_count}`
- dB前有限线性像元数：`{finite_linear_pixel_count}`
- 负线性功率像元数：`{negative_linear_pixel_count}`
- 零值线性功率像元数：`{zero_linear_pixel_count}`

## 限制

- 输入必须是单波段、非负线性功率值；
- 所有栅格与裁剪面必须使用相同CRS；
- 显示增强只作用于独立8位产品，不改变Float32科学像元；
- 本阶段不输出最终SAR专题图。
""")
    return template.format(
        status=report["status"],
        run_id=report["run_id"],
        raster_count=report["inspection"]["raster_count"],
        crs=report["inspection"]["crs"],
        x_resolution=parameters["x_resolution"],
        y_resolution=parameters["y_resolution"],
        display_method=parameters["display_method"],
        warning_text=warning_text,
        db_value_semantics=parameters["db_value_semantics"],
        nan_safe_vrt=parameters["nan_safe_vrt"],
        estimated_gib=parameters["mask_limited_grid_estimate"][
            "three_stage_uncompressed_gib"
        ],
        mosaic_linear=report["artifacts"]["mosaic_linear"],
        clip_linear=report["artifacts"]["clip_linear"],
        db_raster=report["artifacts"]["db_raster"],
        display_raster=report["artifacts"].get("display_raster") or _tr("未生成"),
        display_minimum=report["display"]["minimum"],
        display_maximum=report["display"]["maximum"],
        clip_db_grid_equal=report["acceptance"]["clip_db_grid_equal"],
        source_integrity_pass=report["acceptance"]["source_integrity_pass"],
        valid_pixel_count=report["db"]["valid_pixel_count"],
        finite_linear_pixel_count=report["db"]["finite_linear_pixel_count"],
        negative_linear_pixel_count=report["db"]["negative_linear_pixel_count"],
        zero_linear_pixel_count=report["db"]["zero_linear_pixel_count"],
    )


def execute_sar_job(
    settings: SarJobSettings,
    *,
    progress: ProgressCallback = None,
    is_cancelled: CancelCallback = None,
    run_id: str | None = None,
) -> SarJobResult:
    preflight = preflight_sar_job(
        settings,
        progress=_scaled_progress(progress, 0, 4),
        is_cancelled=is_cancelled,
    )
    if preflight["status"] != "PASS":
        separator = "; " if language_code() == "en" else "；"
        raise ValueError(separator.join(preflight["errors"]))
    paths = [
        Path(value).expanduser().resolve()
        for value in settings.raster_paths
    ]
    mask_path = Path(settings.mask_path).expanduser().resolve()
    mask_source_files = _mask_source_files(mask_path)
    output_root = Path(settings.output_root).expanduser().resolve()
    resolved = preflight["resolved_parameters"]
    task_spec = TaskSpec(
        module_id="sar_mosaic_clip_db",
        module_version=VERSION,
        inputs={
            "rasters": [
                {
                    "source_order": index,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                }
                for index, path in enumerate(paths, start=1)
            ],
            "mask": {
                "path": str(mask_path),
                "size_bytes": mask_path.stat().st_size,
                "physical_files": [
                    str(path) for path in mask_source_files
                ],
            },
        },
        parameters=resolved,
    )
    context = RunContext.create(
        output_root,
        task_spec,
        run_id=run_id or default_run_id(),
        metadata_subdir=RUN_INFO_DIR,
    )
    context.mark_running()
    run_dir = context.run_dir
    run_info = context.metadata_dir
    mosaic_dir = run_dir / MOSAIC_DIR
    clip_dir = run_dir / CLIP_DIR
    db_dir = run_dir / DB_DIR
    quality_dir = run_dir / QUALITY_DIR
    display_dir = run_dir / DISPLAY_DIR
    try:
        for directory in (
            mosaic_dir,
            clip_dir,
            db_dir,
            quality_dir,
            *([display_dir] if settings.create_display_product else []),
        ):
            directory.mkdir(exist_ok=False)
    except Exception as exc:
        context.mark_failed(exc)
        raise

    mosaic_path = mosaic_dir / "sar_mosaic_linear.tif"
    clip_path = clip_dir / "sar_mosaic_clip_linear.tif"
    db_path = db_dir / "sar_mosaic_clip_db.tif"
    display_path = display_dir / "sar_display_rgba_8bit.tif"
    report_json = quality_dir / "sar_processing_report.json"
    report_md = quality_dir / "sar_processing_report.md"
    user_readme = run_dir / "成果说明.md"

    try:
        _emit(progress, 5, _tr("正在计算输入文件SHA-256……"))
        input_hashes_before = _hash_inputs(
            [*paths, *mask_source_files],
            progress=progress,
            is_cancelled=is_cancelled,
            start=5,
            end=15,
        )
        _write_json_exclusive(
            run_info / "input_manifest.json",
            {
                "source_order": [
                    {
                        "order": index,
                        "path": str(path),
                        "sha256": input_hashes_before[str(path)],
                    }
                    for index, path in enumerate(paths, start=1)
                ],
                "mask": {
                    **preflight["mask"],
                    "sha256": input_hashes_before[str(mask_path)],
                    "physical_files": [
                        {
                            "path": str(path),
                            "sha256": input_hashes_before[str(path)],
                        }
                        for path in mask_source_files
                    ],
                },
                "inspection": preflight["inspection"],
                "parameters": resolved,
                "rules": {
                    "overlap": (
                        "later valid pixels overwrite earlier valid pixels"
                    ),
                    "nodata": (
                        "intrinsic source NoData plus NaN-safe temporary VRT; "
                        "output NoData "
                        f"{settings.output_nodata}"
                    ),
                    "radiometry": (
                        "no automatic seamline or physical radiometric balancing; "
                        "optional outer-edge feathering affects display product only"
                    ),
                },
                "scientific_warnings": preflight["warnings"],
                "limitations": preflight["limitations"],
            },
        )

        _emit(progress, 17, _tr("步骤1/4：统一网格并镶嵌线性功率影像。"))
        mosaic_info = mosaic_to_common_grid(
            paths,
            mosaic_path,
            preflight["inspection"],
            x_resolution=resolved["x_resolution"],
            y_resolution=resolved["y_resolution"],
            resampling=settings.mosaic_resampling,
            output_nodata=settings.output_nodata,
            output_bounds=resolved["processing_bounds"],
            progress=_scaled_progress(progress, 17, 48),
            is_cancelled=is_cancelled,
        )

        _emit(progress, 50, _tr("步骤2/4：按矢量掩膜裁剪。"))
        clip_info = clip_mosaic(
            mosaic_path,
            mask_path,
            clip_path,
            resampling=settings.clip_resampling,
            output_nodata=settings.output_nodata,
            progress=_scaled_progress(progress, 50, 66),
            is_cancelled=is_cancelled,
        )

        _emit(progress, 68, _tr("步骤3/4：线性功率转dB。"))
        db_info = linear_power_to_db(
            clip_path,
            db_path,
            output_nodata=settings.output_nodata,
            value_semantics=str(
                preflight["resolved_parameters"]["db_value_semantics"]
            ),
            progress=_scaled_progress(progress, 68, 85),
            is_cancelled=is_cancelled,
        )

        _emit(progress, 87, _tr("步骤4/4：计算显示范围与质量门。"))
        _check_cancelled(is_cancelled)
        display_statistics = sampled_display_statistics(
            db_path,
            method=settings.display_method,
            low_percentile=settings.stretch_low,
            high_percentile=settings.stretch_high,
        )
        display_min = float(display_statistics["display_minimum"])
        display_max = float(display_statistics["display_maximum"])
        display_info = None
        if settings.create_display_product:
            display_info = create_display_product(
                db_path,
                display_path,
                statistics=display_statistics,
                color_mode=settings.color_mode,
                color_ramp=settings.color_ramp,
                brightness=settings.brightness,
                contrast=settings.contrast,
                gamma=settings.gamma,
                feather_pixels=settings.feather_pixels,
                progress=_scaled_progress(progress, 87, 90),
                is_cancelled=is_cancelled,
            )
        clip_db_equal = grids_equal(clip_info, db_info)

        _emit(progress, 90, _tr("正在复核输入文件完整性……"))
        input_hashes_after = _hash_inputs(
            [*paths, *mask_source_files],
            progress=progress,
            is_cancelled=is_cancelled,
            start=90,
            end=97,
        )
        source_integrity = all(
            input_hashes_before[key] == input_hashes_after[key]
            for key in input_hashes_before
        )
        acceptance = {
            "clip_db_grid_equal": clip_db_equal,
            "source_integrity_pass": source_integrity,
            "display_range_valid": display_min < display_max,
            "db_has_valid_pixels": db_info["valid_pixel_count"] > 0,
            "linear_nonpositive_pixels_accounted_for": (
                db_info["valid_pixel_count"]
                + db_info["nonpositive_linear_pixel_count"]
                == db_info["finite_linear_pixel_count"]
            ),
            "negative_linear_power_policy_pass": (
                db_info["negative_linear_pixel_count"] == 0
                or settings.acknowledge_cubic_resampling
            ),
            "display_product_policy_pass": (
                display_info is not None
                if settings.create_display_product
                else True
            ),
        }
        status = "PASS" if all(acceptance.values()) else "FAIL"
        artifacts = {
            "user_readme": str(user_readme),
            "mosaic_linear": str(mosaic_path),
            "clip_linear": str(clip_path),
            "db_raster": str(db_path),
            "report_json": str(report_json),
            "report_md": str(report_md),
            "display_raster": (
                str(display_path) if settings.create_display_product else ""
            ),
        }
        report = {
            "status": status,
            "run_id": run_dir.name,
            "script_version": VERSION,
            "workflow": (
                "explicit order -> mosaic -> clip -> "
                "10log10 dB -> display stretch"
            ),
            "inspection": preflight["inspection"],
            "scientific_warnings": preflight["warnings"],
            "mask": preflight["mask"],
            "parameters": resolved,
            "mosaic": mosaic_info,
            "clip": clip_info,
            "db": db_info,
            "display": {
                "method": settings.display_method,
                "low_percentile": settings.stretch_low,
                "high_percentile": settings.stretch_high,
                "minimum": display_min,
                "maximum": display_max,
                "brightness": settings.brightness,
                "contrast": settings.contrast,
                "gamma": settings.gamma,
                "color_mode": settings.color_mode,
                "color_ramp": settings.color_ramp,
                "feather_pixels": settings.feather_pixels,
                "statistics": display_statistics,
                "product": display_info,
                "changes_pixel_values": False,
                "scientific_raster_unchanged": True,
            },
            "input_hashes_before": input_hashes_before,
            "input_hashes_after": input_hashes_after,
            "acceptance": acceptance,
            "artifacts": artifacts,
            "limitations": preflight["limitations"],
        }
        _write_json_exclusive(report_json, report)
        _write_text_exclusive(
            report_md,
            _render_markdown_report(report),
        )
        if status != "PASS":
            raise RuntimeError(_tr("一个或多个质量门未通过。"))
        _write_text_exclusive(
            user_readme,
            _render_user_readme(
                run_id=run_dir.name,
                input_count=len(paths),
                display_min=display_min,
                display_max=display_max,
                settings=settings,
            ),
        )
        context.mark_pass(
            {
                "status": "PASS",
                "artifacts": artifacts,
                "display_min": display_min,
                "display_max": display_max,
            }
        )
        _emit(progress, 100, _tr("SAR 影像镶嵌、裁剪与显示增强任务完成。"))
        return SarJobResult(
            run_dir=run_dir,
            report_path=report_json,
            artifacts=artifacts,
            display_min=display_min,
            display_max=display_max,
        )
    except SarCancelled as exc:
        if context.status == RunStatus.RUNNING:
            context.mark_cancelled(str(exc))
        raise
    except Exception as exc:
        if context.status == RunStatus.RUNNING:
            try:
                _write_json_exclusive(
                    run_info / "sar_failure_detail.json",
                    {
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                )
            finally:
                context.mark_failed(exc)
        raise
