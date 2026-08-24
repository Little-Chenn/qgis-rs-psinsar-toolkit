"""Settings and read-only validation for cumulative-displacement batch maps."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .localization import tr


BATCH_ENGINE_VERSION = "m7.2.2.1"
FULL_LAYER_NAME = "ps_timeseries_points"
TIME_CATALOG_NAME = "time_catalog"
DEFAULT_DPI = 300
DEFAULT_GRID_SIZE_M = 50.0
DEFAULT_DISPLAY_BOUND_MM = 20.0
# Backward-compatible internal alias. Stored values are millimetres; the old
# constant name is retained so existing integrations do not break.
DEFAULT_DISPLAY_BOUND_M = DEFAULT_DISPLAY_BOUND_MM
DEFAULT_DATA_SOURCE = "PS-InSAR监测成果"
DEFAULT_TITLE_PATTERN = (
    "厦门岛 PS-InSAR 累计垂直形变量空间分布图"
    "（{initial_date}—{target_date}）"
)
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


def localized_default_data_source() -> str:
    return _tr("PS-InSAR监测成果")


def localized_default_title_pattern() -> str:
    return _tr(
        "厦门岛 PS-InSAR 累计垂直形变量空间分布图"
        "（{initial_date}—{target_date}）"
    )


DATE_FIELD_PATTERN = re.compile(r"^D_(\d{4})(\d{2})(\d{2})$")


@dataclass(frozen=True)
class TimeField:
    ordinal: int
    field_name: str
    acquisition_date: str
    unit: str
    is_initial: bool


@dataclass(frozen=True)
class BatchMapSettings:
    input_gpkg: str
    template_path: str
    basemap_path: str
    output_root: str
    selected_fields: tuple[str, ...]
    include_initial_map: bool
    title_pattern: str
    show_data_source: bool
    data_source: str
    show_monitoring_period: bool
    show_production_date: bool
    production_date: str
    show_production_unit: bool
    production_unit: str
    export_qgz: bool
    export_png: bool
    export_pdf: bool
    dpi: int
    grid_size_m: float = DEFAULT_GRID_SIZE_M
    display_bound_m: float = DEFAULT_DISPLAY_BOUND_M


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def read_time_catalog(gpkg_path: str | Path) -> list[TimeField]:
    path = Path(gpkg_path).expanduser().resolve()
    connection = sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro",
        uri=True,
    )
    try:
        columns = {
            str(row[1])
            for row in connection.execute(
                f"PRAGMA table_info({_quote_identifier(TIME_CATALOG_NAME)})"
            ).fetchall()
        }
        required = {
            "ordinal",
            "field_name",
            "acquisition_date",
            "is_initial",
        }
        missing = sorted(required - columns)
        if missing:
            raise ValueError(
                _tr("time_catalog 缺少必要字段：{fields}").format(
                    fields=", ".join(missing)
                )
            )
        if "displacement_unit" in columns:
            unit_column = "displacement_unit"
        elif "unit" in columns:
            unit_column = "unit"
        else:
            raise ValueError(
                _tr(
                    "time_catalog 缺少单位字段 "
                    "displacement_unit（或兼容字段 unit）"
                )
            )
        rows = connection.execute(
            "SELECT ordinal, field_name, acquisition_date, "
            f"{_quote_identifier(unit_column)}, is_initial "
            f"FROM {_quote_identifier(TIME_CATALOG_NAME)} "
            "ORDER BY ordinal"
        ).fetchall()
    finally:
        connection.close()
    return [
        TimeField(
            ordinal=int(row[0]),
            field_name=str(row[1]),
            acquisition_date=str(row[2]),
            unit=str(row[3]),
            is_initial=bool(row[4]),
        )
        for row in rows
    ]


def format_date_field(field_name: str) -> str:
    match = DATE_FIELD_PATTERN.fullmatch(field_name)
    if match is None:
        raise ValueError(_tr("无法解析时相字段：{field}").format(field=field_name))
    parsed = date(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
    )
    return parsed.isoformat()


def validate_batch_settings(
    settings: BatchMapSettings,
    *,
    bundled_template: str | Path | None = None,
) -> list[str]:
    errors: list[str] = []
    gpkg = Path(settings.input_gpkg).expanduser()
    if not settings.input_gpkg.strip():
        errors.append(_tr("请选择PS-InSAR多时相GeoPackage。"))
    elif gpkg.suffix.lower() != ".gpkg" or not gpkg.is_file():
        errors.append(_tr("多时相输入必须是存在的.gpkg文件。"))

    template_value = settings.template_path.strip()
    if not template_value and bundled_template is not None:
        template_value = str(bundled_template)
    template = Path(template_value).expanduser()
    if not template_value:
        errors.append(_tr("请选择累计形变专题图QPT模板。"))
    elif template.suffix.lower() != ".qpt" or not template.is_file():
        errors.append(_tr("累计形变模板必须是存在的.qpt文件。"))

    basemap = Path(settings.basemap_path).expanduser()
    if not settings.basemap_path.strip():
        errors.append(_tr("请选择本地卫星影像底图。"))
    elif basemap.suffix.lower() not in {
        ".tif",
        ".tiff",
        ".vrt",
        ".jp2",
        ".img",
    }:
        errors.append(_tr("底图应为TIF、TIFF、VRT、JP2或IMG。"))
    elif not basemap.is_file():
        errors.append(_tr("选择的底图不存在。"))

    output_root = Path(settings.output_root).expanduser()
    if not settings.output_root.strip():
        errors.append(_tr("请选择输出根目录。"))
    elif not output_root.is_dir():
        errors.append(_tr("输出根目录不存在或不是文件夹。"))

    selected = tuple(settings.selected_fields)
    if not selected:
        errors.append(_tr("请至少选择一个输出时相。"))
    elif len(set(selected)) != len(selected):
        errors.append(_tr("输出时相不能重复。"))
    for field_name in selected:
        try:
            format_date_field(field_name)
        except ValueError as exc:
            errors.append(str(exc))

    if gpkg.is_file():
        try:
            catalog = read_time_catalog(gpkg)
            catalog_names = {item.field_name for item in catalog}
            initial = [item for item in catalog if item.is_initial]
            if len(initial) != 1:
                errors.append(_tr("time_catalog必须且只能标记一个初始时相。"))
            missing = sorted(set(selected) - catalog_names)
            if missing:
                errors.append(
                    _tr("所选时相不在time_catalog中：{fields}").format(
                        fields=", ".join(missing)
                    )
                )
            if initial and not settings.include_initial_map:
                if initial[0].field_name in selected:
                    errors.append(
                        _tr("未启用D0图时，所选时相不能包含初始字段。")
                    )
            units = {item.unit for item in catalog}
            if units != {"mm"}:
                errors.append(_tr("time_catalog的形变量单位必须统一为mm。"))
        except (sqlite3.Error, OSError, ValueError) as exc:
            errors.append(_tr("无法读取多时相目录：{error}").format(error=exc))

    if "{initial_date}" not in settings.title_pattern:
        errors.append(_tr("标题格式必须包含{initial_date}。"))
    if "{target_date}" not in settings.title_pattern:
        errors.append(_tr("标题格式必须包含{target_date}。"))

    if settings.show_data_source and not settings.data_source.strip():
        errors.append(_tr("已勾选数据来源，请填写内容。"))
    if settings.show_production_date:
        try:
            date.fromisoformat(settings.production_date)
        except ValueError:
            errors.append(_tr("制图时间必须是有效的公历日期。"))
    if (
        settings.show_production_unit
        and not settings.production_unit.strip()
    ):
        errors.append(_tr("已勾选制作单位，请填写内容。"))

    if not (settings.export_qgz or settings.export_png or settings.export_pdf):
        errors.append(_tr("请至少选择一种输出：QGZ、PNG或PDF。"))
    if not 72 <= settings.dpi <= 1200:
        errors.append(_tr("DPI必须在72到1200之间。"))
    if settings.grid_size_m != DEFAULT_GRID_SIZE_M:
        errors.append(_tr("当前人工验收模板固定使用50米网格。"))
    if settings.display_bound_m != DEFAULT_DISPLAY_BOUND_M:
        errors.append(_tr("当前人工验收方案固定使用±20 mm统一色标。"))
    return errors
