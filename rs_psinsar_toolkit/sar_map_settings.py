"""Pure-Python settings, validation and text wrapping for SAR maps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
import unicodedata

from .localization import language_code, tr
from .version import PLUGIN_VERSION


TRANSLATION_CONTEXT = "@default"
DEFAULT_SAR_MAP_TITLE = "BC2 VV SAR 强度 dB 专题图"
DEFAULT_DISPLAY_METHOD = "2%—98%线性拉伸"
DEFAULT_SAR_MAP_DPI = 300
SAR_MAP_VERSION = PLUGIN_VERSION
MAX_RIGHT_PANEL_LINES = 8


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


def localized_default_title() -> str:
    return _tr("BC2 VV SAR 强度 dB 专题图")


def localized_default_display_method() -> str:
    return _tr("2%—98%线性拉伸")


@dataclass(frozen=True)
class SarMapSettings:
    """Serializable choices collected by the SAR thematic-map GUI."""

    raster_path: str
    output_root: str
    title: str
    show_crs: bool
    crs_text: str
    show_resolution: bool
    resolution_text: str
    show_display_method: bool
    display_method_text: str
    show_data_source: bool
    data_source: str
    show_acquisition_time: bool
    acquisition_time: str
    show_production_date: bool
    production_date: str
    use_current_date: bool
    show_production_unit: bool
    production_unit: str
    export_qgz: bool
    export_png: bool
    export_pdf: bool
    dpi: int


def validate_sar_map_settings(settings: SarMapSettings) -> list[str]:
    """Return user-facing validation errors without changing state."""
    errors: list[str] = []
    raster_path = Path(settings.raster_path)
    if not settings.raster_path.strip():
        errors.append(_tr("请选择单波段 SAR 强度 dB GeoTIFF。"))
    elif raster_path.suffix.lower() not in {".tif", ".tiff"}:
        errors.append(_tr("SAR 强度专题图输入必须为 TIF 或 TIFF。"))
    elif not raster_path.is_file():
        errors.append(_tr("选择的 SAR 强度 dB GeoTIFF 不存在。"))

    output_root = Path(settings.output_root)
    if not settings.output_root.strip():
        errors.append(_tr("请选择输出根目录。"))
    elif not output_root.is_dir():
        errors.append(_tr("输出根目录不存在或不是文件夹。"))

    if not settings.title.strip():
        errors.append(_tr("专题图标题不能为空。"))

    optional_values = (
        (settings.show_crs, settings.crs_text, _tr("坐标参考系")),
        (settings.show_resolution, settings.resolution_text, _tr("空间分辨率")),
        (
            settings.show_display_method,
            settings.display_method_text,
            _tr("显示方法"),
        ),
        (settings.show_data_source, settings.data_source, _tr("数据来源")),
        (
            settings.show_acquisition_time,
            settings.acquisition_time,
            _tr("数据拍摄时间"),
        ),
        (
            settings.show_production_unit,
            settings.production_unit,
            _tr("制作单位"),
        ),
    )
    for enabled, value, label in optional_values:
        if enabled and not value.strip():
            errors.append(
                _tr("已勾选显示“{label}”，请填写相应内容。").format(
                    label=label
                )
            )

    if settings.show_production_date:
        if not settings.production_date.strip():
            errors.append(_tr("已勾选显示制图时间，请选择日期。"))
        else:
            try:
                date.fromisoformat(settings.production_date)
            except ValueError:
                errors.append(_tr("制图时间必须是有效的公历日期。"))

    if not (settings.export_qgz or settings.export_png or settings.export_pdf):
        errors.append(_tr("请至少选择一种输出：QGZ、PNG 或 PDF。"))
    if not 72 <= settings.dpi <= 1200:
        errors.append(_tr("DPI 必须在 72 到 1200 之间。"))
    right_line_count = len(compose_right_panel(settings).splitlines())
    if right_line_count > MAX_RIGHT_PANEL_LINES:
        errors.append(
            _tr(
                "右侧说明自动换行后超过 {maximum} 行，请精简坐标参考系、空间分辨率或显示方法。"
            ).format(maximum=MAX_RIGHT_PANEL_LINES)
        )
    return errors


def clean_user_text(value: str) -> str:
    """Normalize each user-entered line while preserving explicit breaks."""
    lines = []
    for raw_line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def text_display_units(value: str) -> int:
    """Approximate rendered width using East Asian full-width semantics."""
    return sum(
        2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        for char in value
    )


def _split_long_token(value: str, width: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    current_width = 0
    for char in value:
        char_width = text_display_units(char)
        if current and current_width + char_width > width:
            chunks.append(current)
            current = char
            current_width = char_width
        else:
            current += char
            current_width += char_width
    if current:
        chunks.append(current)
    return chunks


def wrap_user_text(value: str, width: int) -> list[str]:
    """Wrap mixed Latin/CJK text by approximate rendered width."""
    cleaned = clean_user_text(value)
    if not cleaned:
        return []
    wrapped: list[str] = []
    for paragraph in cleaned.split("\n"):
        line = ""
        line_width = 0
        for token in paragraph.split(" "):
            token_width = text_display_units(token)
            separator_width = 1 if line else 0
            if line and line_width + separator_width + token_width <= width:
                line += " " + token
                line_width += separator_width + token_width
                continue
            if line:
                wrapped.append(line)
                line = ""
                line_width = 0
            if token_width <= width:
                line = token
                line_width = token_width
                continue
            token_chunks = _split_long_token(token, width)
            wrapped.extend(token_chunks[:-1])
            line = token_chunks[-1]
            line_width = text_display_units(line)
        if line:
            wrapped.append(line)
    return wrapped


def format_optional_field(
    label: str,
    value: str,
    *,
    width: int,
    split_long_value: bool,
) -> list[str]:
    """Format one optional field without leaving a hidden placeholder."""
    cleaned = clean_user_text(value)
    if not cleaned:
        return []
    separator = ": " if language_code() == "en" else "："
    prefix = f"{label}{separator}"
    combined = prefix + cleaned
    if "\n" not in cleaned and text_display_units(combined) <= width:
        return [combined]
    if split_long_value:
        return [prefix, *wrap_user_text(cleaned, width)]
    continuation_width = max(4, width - text_display_units(prefix))
    value_lines = wrap_user_text(cleaned, continuation_width)
    if not value_lines:
        return [prefix]
    return [prefix + value_lines[0], *value_lines[1:]]


def compose_right_panel(settings: SarMapSettings, width: int = 18) -> str:
    """Compose the three right-side fields with automatic line wrapping."""
    lines: list[str] = []
    fields = (
        (settings.show_crs, _tr("坐标参考系"), settings.crs_text),
        (settings.show_resolution, _tr("空间分辨率"), settings.resolution_text),
        (
            settings.show_display_method,
            _tr("显示方法"),
            settings.display_method_text,
        ),
    )
    for enabled, label, value in fields:
        if enabled:
            lines.extend(
                format_optional_field(
                    label,
                    value,
                    width=width,
                    split_long_value=True,
                )
            )
    return "\n".join(lines)


def compose_source_panel(settings: SarMapSettings, width: int = 42) -> str:
    """Compose the two lower-left fields without blank lines."""
    lines: list[str] = []
    fields = (
        (settings.show_data_source, _tr("数据来源"), settings.data_source),
        (
            settings.show_acquisition_time,
            _tr("数据拍摄时间"),
            settings.acquisition_time,
        ),
    )
    for enabled, label, value in fields:
        if enabled:
            lines.extend(
                format_optional_field(
                    label,
                    value,
                    width=width,
                    split_long_value=False,
                )
            )
    return "\n".join(lines)


def compose_production_panel(
    settings: SarMapSettings,
    formatted_date: str,
    width: int = 28,
) -> str:
    """Compose the two lower-right fields without blank lines."""
    lines: list[str] = []
    if settings.show_production_date:
        lines.extend(
            format_optional_field(
                _tr("制图时间"),
                formatted_date,
                width=width,
                split_long_value=False,
            )
        )
    if settings.show_production_unit:
        lines.extend(
            format_optional_field(
                _tr("制作单位"),
                settings.production_unit,
                width=width,
                split_long_value=False,
            )
        )
    return "\n".join(lines)
