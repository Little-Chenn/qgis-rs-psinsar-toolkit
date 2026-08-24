"""Read-only multi-point PS-InSAR time-series extraction and reporting."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
import statistics
import traceback
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .localization import language_code, tr
from .timeseries_settings import (
    InputInspection,
    TARGET_STRATA,
    TimeSeriesSettings,
    inspect_inputs,
    validate_settings,
)


ENGINE_VERSION = "m9.0.0"
Progress = Callable[[int, str], None]
CancelCheck = Callable[[], bool]
_TR_CONTEXT = "@default"


def _tr(source: str) -> str:
    return tr(_TR_CONTEXT, source)


class TimeSeriesCancelled(RuntimeError):
    """Raised at a safe cancellation gate."""


class TimeSeriesRunError(RuntimeError):
    """Raised when the workflow cannot produce a trustworthy result."""


@dataclass(frozen=True)
class TimeSeriesRunResult:
    run_dir: Path
    point_count: int
    date_count: int
    artifacts: dict[str, str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _snapshot(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _cancel_gate(is_cancelled: CancelCheck, message: str) -> None:
    if is_cancelled():
        raise TimeSeriesCancelled(message)


def descriptive_summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise TimeSeriesRunError(_tr("时序值为空。"))
    steps = [
        values[index] - values[index - 1]
        for index in range(1, len(values))
    ]
    summary = {
        "first_mm": values[0],
        "last_mm": values[-1],
        "net_change_mm": values[-1] - values[0],
        "minimum_mm": min(values),
        "maximum_mm": max(values),
        "range_mm": max(values) - min(values),
        "mean_mm": statistics.fmean(values),
        "median_mm": statistics.median(values),
        "max_absolute_step_mm": max((abs(value) for value in steps), default=0.0),
        # Deprecated aliases retained for scripts written against dev.7.
        "first_m": values[0],
        "last_m": values[-1],
        "net_change_m": values[-1] - values[0],
        "minimum_m": min(values),
        "maximum_m": max(values),
        "range_m": max(values) - min(values),
        "mean_m": statistics.fmean(values),
        "median_m": statistics.median(values),
        "max_absolute_step_m": max((abs(value) for value in steps), default=0.0),
    }
    return summary


def _read_points(
    gpkg: Path,
    inspection: InputInspection,
    progress: Progress,
    is_cancelled: CancelCheck,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[datetime]]:
    field_names = [item.field_name for item in inspection.fields]
    dates = [
        datetime.strptime(item.acquisition_date, "%Y-%m-%d")
        for item in inspection.fields
    ]
    quoted_dates = ", ".join(f'"{name}"' for name in field_names)
    sql = (
        "SELECT fid, ps_uid, source_part, source_fid, velocity, coherence, "
        f"lon, lat, {quoted_dates} "
        "FROM ps_timeseries_points WHERE fid=?"
    )
    fallback_sql = sql.replace("WHERE fid=?", "WHERE ps_uid=?")
    connection = sqlite3.connect(
        f"file:{gpkg.as_posix()}?mode=ro", uri=True
    )
    connection.execute("PRAGMA query_only=ON")
    summaries: list[dict[str, Any]] = []
    long_rows: list[dict[str, Any]] = []
    try:
        for index, selected in enumerate(inspection.selection, start=1):
            _cancel_gate(
                is_cancelled,
                _tr("读取 ps_uid={ps_uid} 前取消。").format(
                    ps_uid=selected["ps_uid"]
                ),
            )
            row = connection.execute(sql, (selected["ps_uid"],)).fetchone()
            if row is None or int(row[1]) != int(selected["ps_uid"]):
                row = connection.execute(
                    fallback_sql, (selected["ps_uid"],)
                ).fetchone()
            if row is None:
                raise TimeSeriesRunError(
                    _tr(
                        "ps_timeseries_points 中找不到 ps_uid={ps_uid}。"
                    ).format(ps_uid=selected["ps_uid"])
                )
            values = [float(value) for value in row[8:] if value is not None]
            if len(values) != len(field_names) or not all(
                math.isfinite(value) for value in values
            ):
                raise TimeSeriesRunError(
                    _tr(
                        "ps_uid={ps_uid} 存在空值或非有限时序值。"
                    ).format(ps_uid=selected["ps_uid"])
                )
            authoritative = {
                **selected,
                "ps_uid": int(row[1]),
                "source_part": int(row[2]),
                "source_fid": int(row[3]),
                "velocity_mm_per_year": float(row[4]),
                "coherence": float(row[5]),
                "lon": float(row[6]),
                "lat": float(row[7]),
                **descriptive_summary(values),
                "date_count": len(field_names),
                "first_date": dates[0].strftime("%Y-%m-%d"),
                "last_date": dates[-1].strftime("%Y-%m-%d"),
            }
            summaries.append(authoritative)
            for field, date, value in zip(field_names, dates, values):
                long_rows.append(
                    {
                        "selection_rank": authoritative["selection_rank"],
                        "ps_uid": authoritative["ps_uid"],
                        "source_part": authoritative["source_part"],
                        "source_fid": authoritative["source_fid"],
                        "review_tier": authoritative["review_tier"],
                        "tail_side": authoritative["tail_side"],
                        "velocity_mm_per_year": authoritative[
                            "velocity_mm_per_year"
                        ],
                        "coherence": authoritative["coherence"],
                        "date_field": field,
                        "observation_date": date.strftime("%Y-%m-%d"),
                        "displacement_mm": value,
                        "displacement_m": value,
                        "positive_direction": "vertical upward",
                        "negative_direction": "vertical downward",
                    }
                )
            progress(
                8 + round(42 * index / inspection.selected_point_count),
                _tr("已回查 {index}/{count} 点").format(
                    index=index,
                    count=inspection.selected_point_count,
                ),
            )
    finally:
        connection.close()
    summaries.sort(key=lambda item: int(item["selection_rank"]))
    long_rows.sort(
        key=lambda item: (int(item["selection_rank"]), item["observation_date"])
    )
    return long_rows, summaries, dates


def _write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> None:
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_points_gpkg(path: Path, summaries: list[dict[str, Any]]) -> None:
    try:
        from osgeo import ogr, osr
    except ImportError as exc:
        raise TimeSeriesRunError(
            _tr("当前 QGIS Python 环境缺少 GDAL/OGR。")
        ) from exc
    ogr.UseExceptions()
    driver = ogr.GetDriverByName("GPKG")
    dataset = driver.CreateDataSource(str(path))
    if dataset is None:
        raise TimeSeriesRunError(_tr("无法创建点位 GeoPackage。"))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    layer = dataset.CreateLayer(
        "selected_timeseries_points", srs=srs, geom_type=ogr.wkbPoint
    )
    fields = [
        ("sel_rank", ogr.OFTInteger),
        ("ps_uid", ogr.OFTInteger64),
        ("src_part", ogr.OFTInteger),
        ("src_fid", ogr.OFTInteger64),
        ("tier", ogr.OFTString),
        ("side", ogr.OFTString),
        ("vel_mmy", ogr.OFTReal),
        ("coherence", ogr.OFTReal),
        ("d_first_mm", ogr.OFTReal),
        ("d_last_mm", ogr.OFTReal),
        ("d_delta_mm", ogr.OFTReal),
        ("d_min_mm", ogr.OFTReal),
        ("d_max_mm", ogr.OFTReal),
        ("d_range_mm", ogr.OFTReal),
        ("max_step_mm", ogr.OFTReal),
        # Deprecated metre-suffixed aliases retained for dev.7 compatibility.
        ("d_first_m", ogr.OFTReal),
        ("d_last_m", ogr.OFTReal),
        ("d_delta_m", ogr.OFTReal),
        ("d_min_m", ogr.OFTReal),
        ("d_max_m", ogr.OFTReal),
        ("d_range_m", ogr.OFTReal),
        ("max_step_m", ogr.OFTReal),
    ]
    for name, kind in fields:
        layer.CreateField(ogr.FieldDefn(name, kind))
    for row in summaries:
        feature = ogr.Feature(layer.GetLayerDefn())
        values = {
            "sel_rank": row["selection_rank"],
            "ps_uid": row["ps_uid"],
            "src_part": row["source_part"],
            "src_fid": row["source_fid"],
            "tier": row["review_tier"],
            "side": row["tail_side"],
            "vel_mmy": row["velocity_mm_per_year"],
            "coherence": row["coherence"],
            "d_first_mm": row["first_mm"],
            "d_last_mm": row["last_mm"],
            "d_delta_mm": row["net_change_mm"],
            "d_min_mm": row["minimum_mm"],
            "d_max_mm": row["maximum_mm"],
            "d_range_mm": row["range_mm"],
            "max_step_mm": row["max_absolute_step_mm"],
            "d_first_m": row["first_m"],
            "d_last_m": row["last_m"],
            "d_delta_m": row["net_change_m"],
            "d_min_m": row["minimum_m"],
            "d_max_m": row["maximum_m"],
            "d_range_m": row["range_m"],
            "max_step_m": row["max_absolute_step_m"],
        }
        for name, value in values.items():
            feature.SetField(name, value)
        geometry = ogr.Geometry(ogr.wkbPoint)
        geometry.AddPoint_2D(float(row["lon"]), float(row["lat"]))
        feature.SetGeometry(geometry)
        layer.CreateFeature(feature)
    dataset = None


def _plot_dependencies():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.font_manager import FontProperties
    except ImportError as exc:
        raise TimeSeriesRunError(
            _tr("当前 QGIS Python 环境缺少 matplotlib。")
        ) from exc
    return mdates, plt, PdfPages, FontProperties


def _font(FontProperties, size: float, bold: bool = False):
    if language_code() == "en":
        candidate = Path(
            r"C:\Windows\Fonts\timesbd.ttf"
            if bold
            else r"C:\Windows\Fonts\times.ttf"
        )
        if candidate.is_file():
            return FontProperties(fname=str(candidate), size=size)
    candidates = (
        Path(r"C:\Windows\Fonts\msyhbd.ttc") if bold else None,
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return FontProperties(fname=str(candidate), size=size)
    return FontProperties(size=size, weight="bold" if bold else "normal")


def _series_by_rank(long_rows: list[dict[str, Any]]) -> dict[int, list[float]]:
    result: dict[int, list[float]] = defaultdict(list)
    for row in long_rows:
        result[int(row["selection_rank"])].append(
            float(row.get("displacement_mm", row["displacement_m"]))
        )
    return result


def _groups(summaries: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in summaries:
        tier = str(row.get("review_tier") or "USER_SELECTED")
        side = str(row.get("tail_side") or "UNSPECIFIED")
        grouped[f"{tier} / {side}"].append(row)
    preferred = [f"{tier} / {side}" for tier, side in TARGET_STRATA]
    ordered = [
        (label, grouped.pop(label)) for label in preferred if label in grouped
    ]
    ordered.extend(sorted(grouped.items(), key=lambda item: item[0]))
    return ordered


def _render_overview(
    path: Path,
    summaries: list[dict[str, Any]],
    long_rows: list[dict[str, Any]],
    dates: list[datetime],
) -> dict[str, int]:
    mdates, plt, _, FontProperties = _plot_dependencies()
    groups = _groups(summaries)
    count = len(groups)
    columns = 2 if count > 1 else 1
    rows = math.ceil(count / columns)
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(15.5, max(4.8, rows * 4.4)),
        squeeze=False,
        sharex=True,
    )
    values = _series_by_rank(long_rows)
    palette = {
        "A_CLUSTER / LOW": "#2563EB",
        "A_CLUSTER / HIGH": "#DC2626",
        "B_ISOLATED / LOW": "#0891B2",
        "B_ISOLATED / HIGH": "#EA580C",
    }
    regular = _font(FontProperties, 10)
    title_font = _font(FontProperties, 16, bold=True)
    for index, (label, group) in enumerate(groups):
        axis = axes.flat[index]
        series = [values[int(row["selection_rank"])] for row in group]
        color = palette.get(label, "#7C3AED")
        for row_values in series:
            axis.plot(dates, row_values, color=color, linewidth=0.8, alpha=0.30)
        median_values = [
            statistics.median(item[date_index] for item in series)
            for date_index in range(len(dates))
        ]
        axis.plot(
            dates,
            median_values,
            color="#111827",
            linewidth=2.0,
            label=_tr("组内中位数"),
        )
        axis.axhline(0.0, color="#6B7280", linewidth=0.8, linestyle="--")
        axis.set_title(
            _tr("{label}（n={count}）").format(
                label=label, count=len(group)
            ),
            fontproperties=regular,
        )
        axis.set_ylabel(_tr("形变量（mm）"), fontproperties=regular)
        axis.grid(True, color="#E5E7EB", linewidth=0.6)
        axis.legend(prop=regular, frameon=False)
        axis.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        axis.tick_params(axis="x", rotation=20)
    for axis in axes.flat[count:]:
        axis.set_visible(False)
    figure.suptitle(
        _tr("PS-InSAR 多点形变时序回查总览"),
        fontproperties=title_font,
        y=0.99,
    )
    figure.text(
        0.5,
        0.012,
        _tr(
            "单位：mm；正值表示垂直向上，负值表示垂直向下；"
            "仅作人工回查，不自动判定异常。"
        ),
        ha="center",
        fontproperties=regular,
    )
    figure.tight_layout(rect=(0.025, 0.04, 0.99, 0.95))
    figure.savefig(path, dpi=180, facecolor="white")
    width, height = figure.canvas.get_width_height()
    plt.close(figure)
    return {"width": int(width), "height": int(height)}


def _render_detail_pdf(
    path: Path,
    summaries: list[dict[str, Any]],
    long_rows: list[dict[str, Any]],
    dates: list[datetime],
) -> int:
    mdates, plt, PdfPages, FontProperties = _plot_dependencies()
    regular = _font(FontProperties, 8.5)
    title_font = _font(FontProperties, 13, bold=True)
    values = _series_by_rank(long_rows)
    pages = 0
    with PdfPages(path) as pdf:
        for start in range(0, len(summaries), 6):
            page_rows = summaries[start : start + 6]
            figure, axes = plt.subplots(2, 3, figsize=(11.69, 8.27), squeeze=False)
            for axis, row in zip(axes.flat, page_rows):
                color = "#2563EB" if row["tail_side"] == "LOW" else "#DC2626"
                axis.plot(
                    dates,
                    values[int(row["selection_rank"])],
                    color=color,
                    linewidth=1.0,
                    marker="o",
                    markersize=1.6,
                )
                axis.axhline(0.0, color="#6B7280", linewidth=0.7, linestyle="--")
                axis.grid(True, color="#E5E7EB", linewidth=0.5)
                axis.set_title(
                    _tr(
                        "#{rank}  ps_uid={ps_uid}\n{tier} / {side}  "
                        "velocity={velocity:.3f} mm/年"
                    ).format(
                        rank=row["selection_rank"],
                        ps_uid=row["ps_uid"],
                        tier=row["review_tier"],
                        side=row["tail_side"],
                        velocity=row["velocity_mm_per_year"],
                    ),
                    fontproperties=regular,
                )
                axis.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
                axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
                axis.tick_params(axis="x", rotation=20)
            for axis in axes.flat[len(page_rows) :]:
                axis.set_visible(False)
            figure.suptitle(
                _tr("PS-InSAR 多点时序明细（形变量单位：mm）"),
                fontproperties=title_font,
            )
            figure.text(
                0.5,
                0.014,
                _tr("正值向上，负值向下；图表仅用于人工回查。"),
                ha="center",
                fontproperties=regular,
            )
            figure.tight_layout(rect=(0.02, 0.04, 0.99, 0.95))
            pdf.savefig(figure, facecolor="white")
            plt.close(figure)
            pages += 1
    return pages


def run_timeseries_review(
    settings: TimeSeriesSettings,
    progress: Progress | None = None,
    is_cancelled: CancelCheck | None = None,
) -> TimeSeriesRunResult:
    progress = progress or (lambda _value, _message: None)
    is_cancelled = is_cancelled or (lambda: False)
    errors = validate_settings(settings)
    if errors:
        separator = "; " if language_code() == "en" else "；"
        raise TimeSeriesRunError(separator.join(errors))
    inspection = inspect_inputs(settings)
    input_gpkg = Path(settings.input_gpkg).expanduser().resolve()
    point_csv = Path(settings.point_csv).expanduser().resolve()
    output_root = Path(settings.output_root).expanduser().resolve()
    run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_timeseries_review")
    run_dir = output_root / run_id
    run_dir.mkdir(exist_ok=False)
    tables_dir = run_dir / "01_数据表"
    points_dir = run_dir / "02_点位图层"
    charts_dir = run_dir / "03_图表"
    qa_dir = run_dir / "04_质量报告"
    for directory in (tables_dir, points_dir, charts_dir, qa_dir):
        directory.mkdir()
    gpkg_before = _snapshot(input_gpkg)
    csv_before = {**_snapshot(point_csv), "sha256": _sha256(point_csv)}
    artifacts: dict[str, str] = {}
    try:
        progress(2, _tr("只读检查输入与时相目录"))
        _cancel_gate(is_cancelled, _tr("输入检查后取消。"))
        long_rows, summaries, dates = _read_points(
            input_gpkg, inspection, progress, is_cancelled
        )
        _cancel_gate(is_cancelled, _tr("读取时序后取消。"))
        if settings.export_csv:
            progress(55, _tr("写入长表和点位摘要表"))
            long_path = tables_dir / "timeseries_long.csv"
            summary_path = tables_dir / "timeseries_summary.csv"
            _write_csv(
                long_path,
                long_rows,
                [
                    "selection_rank", "ps_uid", "source_part", "source_fid",
                    "review_tier", "tail_side", "velocity_mm_per_year",
                    "coherence", "date_field", "observation_date",
                    "displacement_mm", "displacement_m",
                    "positive_direction", "negative_direction",
                ],
            )
            _write_csv(
                summary_path,
                summaries,
                [
                    "selection_rank", "stratum_rank", "ps_uid", "source_part",
                    "source_fid", "review_tier", "tail_side",
                    "velocity_mm_per_year", "coherence", "lon", "lat",
                    "date_count", "first_date", "last_date",
                    "first_mm", "last_mm", "net_change_mm", "minimum_mm",
                    "maximum_mm", "range_mm", "mean_mm", "median_mm",
                    "max_absolute_step_mm", "first_m", "last_m",
                    "net_change_m", "minimum_m", "maximum_m", "range_m",
                    "mean_m", "median_m", "max_absolute_step_m",
                ],
            )
            artifacts["long_csv"] = str(long_path)
            artifacts["summary_csv"] = str(summary_path)
        _cancel_gate(is_cancelled, _tr("表格写入后取消。"))
        if settings.export_gpkg:
            progress(64, _tr("创建可编辑点位 GeoPackage"))
            point_path = points_dir / "selected_timeseries_points.gpkg"
            _write_points_gpkg(point_path, summaries)
            artifacts["point_gpkg"] = str(point_path)
        _cancel_gate(is_cancelled, _tr("点位图层写入后取消。"))
        overview_qa: dict[str, int] | None = None
        if settings.export_png:
            progress(73, _tr("绘制多点时序总览 PNG"))
            overview_path = charts_dir / "timeseries_overview.png"
            overview_qa = _render_overview(
                overview_path, summaries, long_rows, dates
            )
            artifacts["overview_png"] = str(overview_path)
        _cancel_gate(is_cancelled, _tr("总览图输出后取消。"))
        pdf_pages = 0
        if settings.export_pdf:
            progress(84, _tr("绘制逐点时序明细 PDF"))
            pdf_path = charts_dir / "timeseries_detail_book.pdf"
            pdf_pages = _render_detail_pdf(pdf_path, summaries, long_rows, dates)
            artifacts["detail_pdf"] = str(pdf_path)
        _cancel_gate(is_cancelled, _tr("明细 PDF 输出后取消。"))

        gpkg_after = _snapshot(input_gpkg)
        csv_after = {**_snapshot(point_csv), "sha256": _sha256(point_csv)}
        checks = {
            "selected_points_present": len(summaries) == inspection.selected_point_count,
            "long_row_count": len(long_rows)
            == inspection.selected_point_count * len(inspection.fields),
            "all_values_finite": all(
                math.isfinite(float(row["displacement_mm"])) for row in long_rows
            ),
            "date_catalog_complete": len(dates) == len(inspection.fields),
            "unit_is_mm": all(item.unit == "mm" for item in inspection.fields),
            "unit_is_m": False,
            "input_gpkg_unchanged": gpkg_before == gpkg_after,
            "point_csv_unchanged": csv_before == csv_after,
            "overview_created_if_requested": (not settings.export_png)
            or overview_qa is not None,
            "pdf_created_if_requested": (not settings.export_pdf) or pdf_pages > 0,
        }
        acceptance_checks = {
            key: value for key, value in checks.items() if key != "unit_is_m"
        }
        status = "PASS" if all(acceptance_checks.values()) else "REVIEW"
        report = {
            "status": status,
            "module": "PS-InSAR multi-point time-series review",
            "engine_version": ENGINE_VERSION,
            "created_utc": _utc_now(),
            "scientific_semantics": {
                "velocity_unit": "mm/year",
                "displacement_unit": "mm",
                "positive_direction": "vertical upward",
                "negative_direction": "vertical downward",
                "interpretation_policy": (
                    "descriptive review only; no automatic anomaly or physical-cause classification"
                ),
            },
            "inputs": {
                "multi_temporal_gpkg": gpkg_before,
                "point_csv": csv_before,
            },
            "selection": {
                "mode": inspection.point_mode,
                "source_row_count": inspection.source_row_count,
                "selected_point_count": inspection.selected_point_count,
                "quota_per_stratum": settings.quota_per_stratum,
                "minimum_distance_m": settings.minimum_distance_m,
            },
            "timeseries": {
                "date_count": len(dates),
                "first_date": dates[0].strftime("%Y-%m-%d"),
                "last_date": dates[-1].strftime("%Y-%m-%d"),
                "long_row_count": len(long_rows),
            },
            "visuals": {
                "overview": overview_qa,
                "detail_pdf_pages": pdf_pages,
            },
            "settings": asdict(settings),
            "checks": checks,
            "artifacts": artifacts,
        }
        report_path = qa_dir / "timeseries_review_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        markdown_path = qa_dir / "timeseries_review_report.md"
        markdown_path.write_text(
            "\n".join(
                [
                    _tr("# PS-InSAR 多点形变时序回查报告"),
                    "",
                    _tr("状态：`{status}`").format(status=status),
                    "",
                    _tr("- 点位：{count} 个；").format(
                        count=inspection.selected_point_count
                    ),
                    _tr(
                        "- 时相：{count} 期（{first_date}—{last_date}）；"
                    ).format(
                        count=len(dates),
                        first_date=f"{dates[0]:%Y-%m-%d}",
                        last_date=f"{dates[-1]:%Y-%m-%d}",
                    ),
                    _tr("- 形变量单位：mm；正值向上，负值向下；"),
                    _tr(
                        "- 结果仅用于人工回查，不自动判定异常或物理成因；"
                    ),
                    _tr(
                        "- 输入 GeoPackage 与点位 CSV 均保持未修改。"
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        artifacts["qa_json"] = str(report_path)
        artifacts["qa_markdown"] = str(markdown_path)
        (qa_dir / "status_pass.json").write_text(
            json.dumps(
                {"status": status, "updated_utc": _utc_now()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        progress(
            100,
            _tr("多点形变时序回查完成：{status}").format(
                status=status
            ),
        )
        if status != "PASS":
            raise TimeSeriesRunError(
                _tr("质量检查未通过：{path}").format(path=report_path)
            )
        return TimeSeriesRunResult(
            run_dir=run_dir,
            point_count=inspection.selected_point_count,
            date_count=len(dates),
            artifacts=artifacts,
        )
    except TimeSeriesCancelled as exc:
        (qa_dir / "RUN_CANCELLED.md").write_text(
            _tr("# 任务已取消\n\n{message}\n\n输入未被修改。\n").format(
                message=exc
            ),
            encoding="utf-8",
        )
        raise
    except Exception:
        (qa_dir / "RUN_FAILED.md").write_text(
            _tr(
                "# 任务失败\n\n输入未被修改；本 run 保留用于诊断。"
                "\n\n```text\n{traceback}\n```\n"
            ).format(traceback=traceback.format_exc()),
            encoding="utf-8",
        )
        raise
