"""Pure-Python settings and validation for thematic-map jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .localization import tr

DEFAULT_TITLE = "厦门岛 PS-InSAR 垂直形变速率汇总图"
DEFAULT_DPI = 300

INPUT_CURRENT_LAYER = "current_layer"
INPUT_GPKG = "gpkg"

BASEMAP_LOCAL = "local_raster"
BASEMAP_CURRENT_LAYER = "current_layer"
BASEMAP_NONE = "none"
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


def localized_default_title() -> str:
    return _tr("厦门岛 PS-InSAR 垂直形变速率汇总图")


@dataclass(frozen=True)
class MapJobSettings:
    """Serializable user choices collected by the GUI."""

    input_mode: str
    current_layer_id: str
    current_layer_name: str
    vector_path: str
    vector_sublayer: str
    value_field: str
    basemap_mode: str
    local_basemap_path: str
    current_basemap_id: str
    current_basemap_name: str
    output_root: str
    title: str
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


def validate_settings(settings: MapJobSettings) -> list[str]:
    """Return user-facing validation errors without changing any state."""
    errors: list[str] = []

    if settings.input_mode == INPUT_CURRENT_LAYER:
        if not settings.current_layer_id:
            errors.append(_tr("请选择当前工程中的velocity矢量图层。"))
    elif settings.input_mode == INPUT_GPKG:
        vector_path = Path(settings.vector_path)
        if not settings.vector_path.strip():
            errors.append(_tr("请选择GeoPackage文件。"))
        elif vector_path.suffix.lower() != ".gpkg":
            errors.append(_tr("velocity文件必须为.gpkg格式。"))
        elif not vector_path.is_file():
            errors.append(_tr("选择的GeoPackage文件不存在。"))
        elif not settings.vector_sublayer.strip():
            errors.append(_tr("请选择GeoPackage中的velocity图层。"))
    else:
        errors.append(_tr("无法识别velocity输入模式。"))

    if not settings.value_field.strip():
        errors.append(_tr("请选择或填写velocity数值字段。"))

    if settings.basemap_mode == BASEMAP_LOCAL:
        basemap_path = Path(settings.local_basemap_path)
        allowed = {".tif", ".tiff", ".vrt", ".jp2", ".img"}
        if not settings.local_basemap_path.strip():
            errors.append(_tr("请选择本地栅格底图，或改用其他底图模式。"))
        elif basemap_path.suffix.lower() not in allowed:
            errors.append(_tr("本地底图应为TIF、TIFF、VRT、JP2或IMG栅格。"))
        elif not basemap_path.is_file():
            errors.append(_tr("选择的本地栅格底图不存在。"))
    elif settings.basemap_mode == BASEMAP_CURRENT_LAYER:
        if not settings.current_basemap_id:
            errors.append(_tr("请选择当前工程中的栅格或XYZ底图图层。"))
    elif settings.basemap_mode != BASEMAP_NONE:
        errors.append(_tr("无法识别底图模式。"))

    output_root = Path(settings.output_root)
    if not settings.output_root.strip():
        errors.append(_tr("请选择输出根目录。"))
    elif not output_root.is_dir():
        errors.append(_tr("输出根目录不存在或不是文件夹。"))

    if not settings.title.strip():
        errors.append(_tr("专题图标题不能为空。"))

    if settings.show_data_source and not settings.data_source.strip():
        errors.append(_tr("已勾选显示数据来源，请填写数据来源。"))

    if (
        settings.show_acquisition_time
        and not settings.acquisition_time.strip()
    ):
        errors.append(_tr("已勾选显示数据拍摄时间，请填写数据拍摄时间。"))

    if settings.show_production_date:
        if not settings.production_date.strip():
            errors.append(_tr("已勾选显示制图时间，请选择日期。"))
        else:
            try:
                date.fromisoformat(settings.production_date)
            except ValueError:
                errors.append(_tr("制图时间必须是有效的公历日期。"))

    if settings.show_production_unit and not settings.production_unit.strip():
        errors.append(_tr("已勾选显示制作单位，请填写制作单位。"))

    if not (settings.export_qgz or settings.export_png or settings.export_pdf):
        errors.append(_tr("请至少选择一种输出：QGZ、PNG或PDF。"))

    if not 72 <= settings.dpi <= 1200:
        errors.append(_tr("DPI必须在72到1200之间。"))

    return errors
