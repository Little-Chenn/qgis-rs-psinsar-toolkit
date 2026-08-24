"""Non-overwriting PS-InSAR thematic-map generation core."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import traceback
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont, QImage
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsReadWriteContext,
    QgsReferencedRectangle,
    QgsRendererRange,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .localization import language_code, tr
from .settings import (
    BASEMAP_CURRENT_LAYER,
    BASEMAP_LOCAL,
    BASEMAP_NONE,
    INPUT_CURRENT_LAYER,
    INPUT_GPKG,
    MapJobSettings,
    validate_settings,
)
from .version import PLUGIN_VERSION, PS_MAP_ENGINE_VERSION


TEMPLATE_NAME_ZH = "plugin_overview_template_v5.qpt"
TEMPLATE_REPORT_NAME_ZH = "plugin_overview_template_v5_report.json"
TEMPLATE_NAME_EN = "plugin_overview_template_v5_en.qpt"
TEMPLATE_REPORT_NAME_EN = "plugin_overview_template_v5_en_report.json"
NORTH_ARROW_NAME = "north_arrow_simple.svg"
REPORT_NAME = "m41_build_report.json"
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


def _template_names() -> tuple[str, str]:
    if language_code() == "en":
        return TEMPLATE_NAME_EN, TEMPLATE_REPORT_NAME_EN
    return TEMPLATE_NAME_ZH, TEMPLATE_REPORT_NAME_ZH

CLASS_COLORS = [
    "#30123B",
    "#4455C4",
    "#4390FE",
    "#1FC9DD",
    "#2AEFA1",
    "#7EFF55",
    "#C2F234",
    "#F2C93A",
    "#FE8F29",
    "#E94D0D",
    "#BD2002",
    "#7A0403",
]
CLASS_LABELS = [
    "< −5.0",
    "−5.0 – −4.0",
    "−4.0 – −3.0",
    "−3.0 – −2.0",
    "−2.0 – −1.0",
    "−1.0 – \u20070.0",
    "\u20070.0 – \u20071.0",
    "\u20071.0 – \u20072.0",
    "\u20072.0 – \u20073.0",
    "\u20073.0 – \u20074.0",
    "\u20074.0 – \u20075.0",
    "≥ \u20075.0",
]
CORE_BREAKS = [-5.0, -4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0]


class MapBuildError(RuntimeError):
    """Raised when a PS-InSAR map cannot satisfy an acceptance gate."""


class BuildCancelled(RuntimeError):
    """Raised after a cooperative cancellation request."""


@dataclass(frozen=True)
class BuildResult:
    run_dir: Path
    report_path: Path
    status: str
    artifacts: dict[str, str]


ProgressCallback = Callable[[int, str], None]
CancelCallback = Callable[[], bool]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _json_safe(value: object) -> object:
    """Convert QGIS/Qt values into deterministic JSON-compatible values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    is_null = getattr(value, "isNull", None)
    if callable(is_null):
        try:
            if is_null():
                return None
        except (RuntimeError, TypeError):
            pass
    unwrap = getattr(value, "value", None)
    if callable(unwrap):
        try:
            unwrapped = unwrap()
            if unwrapped is not value:
                return _json_safe(unwrapped)
        except (RuntimeError, TypeError):
            pass
    return str(value)


def _write_json_exclusive(path: Path, value: object) -> None:
    payload = json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        indent=2,
    )
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.write("\n")


def _write_text_exclusive(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def _source_file_from_uri(uri: str) -> Path | None:
    candidate = uri.split("|", 1)[0]
    path = Path(candidate)
    return path.resolve() if path.is_file() else None


def _existing_source_files(
    settings: MapJobSettings,
    source_project: QgsProject,
) -> dict[str, Path]:
    files: dict[str, Path] = {}
    if settings.input_mode == INPUT_GPKG:
        vector_path = Path(settings.vector_path).resolve()
        if vector_path.is_file():
            files["velocity"] = vector_path
    elif settings.input_mode == INPUT_CURRENT_LAYER:
        layer = source_project.mapLayer(settings.current_layer_id)
        if layer is not None:
            path = _source_file_from_uri(layer.source())
            if path is not None:
                files["velocity"] = path

    if settings.basemap_mode == BASEMAP_LOCAL:
        path = Path(settings.local_basemap_path).resolve()
        if path.is_file():
            files["basemap"] = path
    elif settings.basemap_mode == BASEMAP_CURRENT_LAYER:
        layer = source_project.mapLayer(settings.current_basemap_id)
        if layer is not None:
            path = _source_file_from_uri(layer.source())
            if path is not None:
                files["basemap"] = path
    return files


def _hash_files(files: dict[str, Path]) -> dict[str, str]:
    return {name: sha256_file(path) for name, path in files.items()}


def _make_run_dir(output_root: Path) -> Path:
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S_%f")[:-3]
    run_dir = output_root / f"{run_id}_m41_thematic_map"
    run_dir.mkdir(parents=False, exist_ok=False)
    return run_dir


def _format_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    if language_code() == "en":
        return parsed.strftime("%Y-%m-%d")
    return _tr("{year}年{month}月{day}日").format(
        year=parsed.year, month=parsed.month, day=parsed.day
    )


def _load_source_vector(
    settings: MapJobSettings,
    source_project: QgsProject,
) -> QgsVectorLayer:
    if settings.input_mode == INPUT_CURRENT_LAYER:
        source = source_project.mapLayer(settings.current_layer_id)
        if source is None or not isinstance(source, QgsVectorLayer):
            raise MapBuildError(_tr("当前工程中的velocity图层已不存在。"))
        layer = source.clone()
        layer.setName(source.name())
    else:
        uri = (
            f"{Path(settings.vector_path).resolve()}"
            f"|layername={settings.vector_sublayer}"
        )
        layer = QgsVectorLayer(uri, settings.vector_sublayer, "ogr")
    if not layer.isValid():
        raise MapBuildError(_tr("QGIS无法只读加载velocity图层。"))
    if layer.featureCount() <= 0:
        raise MapBuildError(_tr("velocity图层没有要素。"))
    if not layer.crs().isValid():
        raise MapBuildError(_tr("velocity图层缺少有效CRS。"))
    if QgsWkbTypes.geometryType(layer.wkbType()) != Qgis.GeometryType.Polygon:
        raise MapBuildError(_tr("当前PS-InSAR专题图仅支持面状velocity网格图层。"))
    field_index = layer.fields().indexFromName(settings.value_field)
    if field_index < 0:
        raise MapBuildError(
            _tr("数值字段不存在：{field}").format(field=settings.value_field)
        )
    if not layer.fields().field(field_index).isNumeric():
        raise MapBuildError(
            _tr("字段不是数值类型：{field}").format(field=settings.value_field)
        )
    return layer


def _copy_vector_layer(
    source_layer: QgsVectorLayer,
    destination: Path,
    transform_context: QgsCoordinateTransformContext,
) -> QgsVectorLayer:
    if destination.exists():
        raise FileExistsError(destination)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "velocity_grid"
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        source_layer,
        str(destination),
        transform_context,
        options,
    )
    if result[0] != QgsVectorFileWriter.NoError:
        raise MapBuildError(
            _tr("复制velocity图层失败：{error}").format(error=result[1])
        )
    layer = QgsVectorLayer(
        f"{destination}|layername=velocity_grid",
        _tr("50米网格垂直形变速率中位数（mm/年）"),
        "ogr",
    )
    if not layer.isValid():
        raise MapBuildError(_tr("插件无法重新加载输出velocity副本。"))
    return layer


def _copy_raster_file(source: Path, data_dir: Path) -> Path:
    suffix = source.suffix.lower() or ".tif"
    destination = data_dir / f"basemap{suffix}"
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copy2(source, destination)
    sidecar_suffixes = [".aux.xml", ".ovr", ".tfw", ".prj"]
    for sidecar_suffix in sidecar_suffixes:
        sidecar = Path(f"{source}{sidecar_suffix}")
        if sidecar.is_file():
            shutil.copy2(sidecar, Path(f"{destination}{sidecar_suffix}"))
    return destination


def _load_basemap(
    settings: MapJobSettings,
    source_project: QgsProject,
    data_dir: Path,
) -> tuple[QgsRasterLayer | None, dict[str, object]]:
    if settings.basemap_mode == BASEMAP_NONE:
        return None, {"mode": BASEMAP_NONE}

    if settings.basemap_mode == BASEMAP_LOCAL:
        source = Path(settings.local_basemap_path).resolve()
        copied = _copy_raster_file(source, data_dir)
        layer = QgsRasterLayer(str(copied), _tr("专题图底图"), "gdal")
        metadata = {
            "mode": BASEMAP_LOCAL,
            "source": str(source),
            "copied_path": str(copied),
            "provider": "gdal",
        }
    else:
        source_layer = source_project.mapLayer(settings.current_basemap_id)
        if source_layer is None or not isinstance(source_layer, QgsRasterLayer):
            raise MapBuildError(_tr("当前工程中的底图图层已不存在。"))
        local_path = _source_file_from_uri(source_layer.source())
        if local_path is not None:
            copied = _copy_raster_file(local_path, data_dir)
            layer = QgsRasterLayer(str(copied), source_layer.name(), "gdal")
            metadata = {
                "mode": BASEMAP_CURRENT_LAYER,
                "source": str(local_path),
                "copied_path": str(copied),
                "provider": "gdal",
            }
        else:
            layer = QgsRasterLayer(
                source_layer.source(),
                source_layer.name(),
                source_layer.providerType(),
            )
            metadata = {
                "mode": BASEMAP_CURRENT_LAYER,
                "source": source_layer.source(),
                "provider": source_layer.providerType(),
                "copied_path": None,
            }
    if not layer.isValid():
        raise MapBuildError(_tr("QGIS无法加载所选底图。"))
    if not layer.crs().isValid():
        raise MapBuildError(_tr("所选底图缺少有效CRS。"))
    return layer, metadata


def _configure_velocity_style(
    layer: QgsVectorLayer,
    value_field: str,
) -> dict[str, object]:
    field_index = layer.fields().indexFromName(value_field)
    minimum = float(layer.minimumValue(field_index))
    maximum = float(layer.maximumValue(field_index))
    if not math.isfinite(minimum) or not math.isfinite(maximum):
        raise MapBuildError(_tr("velocity数值范围无效。"))
    edges = [min(minimum, -5.0), *CORE_BREAKS, max(maximum, 5.0)]
    ranges: list[QgsRendererRange] = []
    for lower, upper, color, label in zip(
        edges[:-1],
        edges[1:],
        CLASS_COLORS,
        CLASS_LABELS,
    ):
        symbol = QgsFillSymbol.createSimple(
            {
                "color": color,
                "outline_style": "no",
            }
        )
        ranges.append(
            QgsRendererRange(float(lower), float(upper), symbol, label)
        )
    layer.setRenderer(QgsGraduatedSymbolRenderer(value_field, ranges))
    layer.setOpacity(0.609)
    layer.setCustomProperty("rs_psinsar/velocity_unit", "mm/year")
    layer.setCustomProperty("rs_psinsar/positive_direction", "vertical upward")
    layer.setCustomProperty("rs_psinsar/negative_direction", "vertical downward")
    layer.setCustomProperty("rs_psinsar/no_feature_outline", True)
    return {
        "field": value_field,
        "minimum": minimum,
        "maximum": maximum,
        "edges": edges,
        "labels": CLASS_LABELS,
        "colors": CLASS_COLORS,
        "opacity": 0.609,
    }


def _transformed_extent(
    layer,
    destination_crs: QgsCoordinateReferenceSystem,
    project: QgsProject,
):
    transform = QgsCoordinateTransform(layer.crs(), destination_crs, project)
    return transform.transformBoundingBox(layer.extent())


def _coverage_ratio(container, content) -> float:
    content_area = content.width() * content.height()
    if content_area <= 0:
        return 0.0
    width = max(
        0.0,
        min(container.xMaximum(), content.xMaximum())
        - max(container.xMinimum(), content.xMinimum()),
    )
    height = max(
        0.0,
        min(container.yMaximum(), content.yMaximum())
        - max(container.yMinimum(), content.yMinimum()),
    )
    return (width * height) / content_area


def _fit_extent_to_ratio(extent, target_ratio: float, margin: float = 0.04):
    result = extent
    result.grow(max(result.width(), result.height()) * margin)
    if result.height() <= 0 or result.width() <= 0:
        raise MapBuildError(_tr("地图范围为空。"))
    current_ratio = result.width() / result.height()
    center_x = result.center().x()
    center_y = result.center().y()
    if current_ratio < target_ratio:
        half_width = result.height() * target_ratio / 2.0
        result.setXMinimum(center_x - half_width)
        result.setXMaximum(center_x + half_width)
    elif current_ratio > target_ratio:
        half_height = result.width() / target_ratio / 2.0
        result.setYMinimum(center_y - half_height)
        result.setYMaximum(center_y + half_height)
    return result


def _layout_item(layout: QgsPrintLayout, item_id: str, expected_type):
    item = layout.itemById(item_id)
    if item is None or not isinstance(item, expected_type):
        raise MapBuildError(
            _tr("派生模板缺少布局项：{item_id}").format(item_id=item_id)
        )
    return item


def _load_and_bind_layout(
    project: QgsProject,
    template_path: Path,
    north_arrow_path: Path,
    grid_layer: QgsVectorLayer,
    basemap_layer: QgsRasterLayer | None,
    settings: MapJobSettings,
) -> tuple[QgsPrintLayout, dict[str, object]]:
    document = QDomDocument()
    ok, message, line, column = document.setContent(
        template_path.read_text(encoding="utf-8")
    )
    if not ok:
        raise MapBuildError(
            _tr("派生QPT XML错误 {line}:{column}：{message}").format(
                line=line, column=column, message=message
            )
        )
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    _, load_ok = layout.loadFromTemplate(
        document,
        QgsReadWriteContext(),
        True,
    )
    if not load_ok:
        raise MapBuildError(_tr("QGIS无法加载派生QPT。"))
    layout.setName(_tr("PS-InSAR专题图（可编辑）"))

    title = _layout_item(layout, "m341_title", QgsLayoutItemLabel)
    title.setText(settings.title)
    map_item = _layout_item(layout, "m341_overview_map", QgsLayoutItemMap)
    legend = _layout_item(
        layout,
        "m341_velocity_legend",
        QgsLayoutItemLegend,
    )
    scale = _layout_item(
        layout,
        "m341_scale_bar",
        QgsLayoutItemScaleBar,
    )
    north = _layout_item(
        layout,
        "m341_north_arrow",
        QgsLayoutItemPicture,
    )
    metadata_left = _layout_item(
        layout,
        "plugin_metadata_left",
        QgsLayoutItemLabel,
    )
    metadata_right = _layout_item(
        layout,
        "plugin_metadata_right",
        QgsLayoutItemLabel,
    )
    for metadata_label in (metadata_left, metadata_right):
        metadata_label.setMode(QgsLayoutItemLabel.Mode.ModeFont)
        text_format = metadata_label.textFormat()
        primary_font = text_format.font()
        primary_font.setFamily("Times New Roman")
        text_format.setFont(primary_font)
        text_format.setFamilies(["Times New Roman", "SimSun"])
        text_format.setAllowHtmlFormatting(False)
        metadata_label.setTextFormat(text_format)

    map_crs = (
        basemap_layer.crs()
        if basemap_layer is not None and basemap_layer.crs().isValid()
        else QgsCoordinateReferenceSystem("EPSG:3857")
    )
    project.setCrs(map_crs)
    map_item.setCrs(map_crs)
    map_layers = [grid_layer]
    if basemap_layer is not None:
        map_layers.append(basemap_layer)
    map_item.setLayers(map_layers)
    map_item.setKeepLayerSet(True)
    map_item.setBackgroundEnabled(True)
    map_item.setBackgroundColor(QColor(255, 255, 255))

    data_extent = _transformed_extent(grid_layer, map_crs, project)
    template_extent = map_item.extent()
    if (
        map_crs.authid() == "EPSG:3857"
        and _coverage_ratio(template_extent, data_extent) >= 0.98
    ):
        map_extent = template_extent
        extent_policy = "confirmed_template_extent"
    else:
        base_extent = (
            _transformed_extent(basemap_layer, map_crs, project)
            if basemap_layer is not None
            else data_extent
        )
        target_ratio = map_item.rect().width() / map_item.rect().height()
        map_extent = _fit_extent_to_ratio(base_extent, target_ratio)
        extent_policy = "automatic_fit"
    map_item.setExtent(map_extent)

    legend.setLinkedMap(map_item)
    legend.setAutoUpdateModel(False)
    legend.model().rootGroup().removeAllChildren()
    legend_node = legend.model().rootGroup().addLayer(grid_layer)
    legend_node.setCustomProperty("legend/title-label", " ")
    legend.setTitle("")
    symbol_label_style = legend.rstyle(
        Qgis.LegendComponent.SymbolLabel
    )
    symbol_label_format = symbol_label_style.textFormat()
    symbol_label_font = symbol_label_format.font()
    symbol_label_font.setFamily("Times New Roman")
    symbol_label_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.0)
    symbol_label_format.setFont(symbol_label_font)
    symbol_label_format.setFamilies(["Times New Roman"])
    symbol_label_style.setTextFormat(symbol_label_format)
    symbol_label_style.setAlignment(Qt.AlignLeft)
    legend.setResizeToContents(True)
    legend.refresh()
    scale.setLinkedMap(map_item)
    north.setPicturePath(str(north_arrow_path.resolve()))

    left_lines: list[str] = []
    if settings.show_data_source:
        left_lines.append(
            _tr("数据来源：{value}").format(value=settings.data_source.strip())
        )
    if settings.show_acquisition_time:
        left_lines.append(
            _tr("数据拍摄时间：{value}").format(
                value=settings.acquisition_time.strip()
            )
        )
    right_lines: list[str] = []
    if settings.show_production_date:
        right_lines.append(
            _tr("制图时间：{value}").format(
                value=_format_date(settings.production_date)
            )
        )
    if settings.show_production_unit:
        right_lines.append(
            _tr("制作单位：{value}").format(
                value=settings.production_unit.strip()
            )
        )
    metadata_left.setVisibility(bool(left_lines))
    metadata_right.setVisibility(bool(right_lines))

    project.layoutManager().addLayout(layout)
    return layout, {
        "layout_name": layout.name(),
        "map_crs": map_crs.authid(),
        "map_extent": [
            map_extent.xMinimum(),
            map_extent.yMinimum(),
            map_extent.xMaximum(),
            map_extent.yMaximum(),
        ],
        "extent_policy": extent_policy,
        "metadata_left_lines": left_lines,
        "metadata_right_lines": right_lines,
        "required_item_ids": [
            "m341_title",
            "m341_overview_map",
            "m341_velocity_legend",
            "m341_scale_bar",
            "m341_north_arrow",
            "plugin_metadata_left",
            "plugin_metadata_right",
        ],
    }


def _export_layout(
    layout: QgsPrintLayout,
    settings: MapJobSettings,
    png_path: Path | None,
    pdf_path: Path | None,
) -> dict[str, object]:
    exporter = QgsLayoutExporter(layout)
    results: dict[str, object] = {}
    if png_path is not None:
        image_settings = QgsLayoutExporter.ImageExportSettings()
        image_settings.dpi = settings.dpi
        code = exporter.exportToImage(str(png_path), image_settings)
        if code != QgsLayoutExporter.Success:
            raise MapBuildError(
                _tr("PNG导出失败，QGIS代码：{code}").format(code=int(code))
            )
        image = QImage(str(png_path))
        if image.isNull():
            raise MapBuildError(_tr("PNG导出后无法重新读取。"))
        results["png"] = {
            "path": str(png_path),
            "width": image.width(),
            "height": image.height(),
            "size_bytes": png_path.stat().st_size,
            "sha256": sha256_file(png_path),
        }
    if pdf_path is not None:
        pdf_settings = QgsLayoutExporter.PdfExportSettings()
        pdf_settings.dpi = settings.dpi
        code = exporter.exportToPdf(str(pdf_path), pdf_settings)
        if code != QgsLayoutExporter.Success:
            raise MapBuildError(
                _tr("PDF导出失败，QGIS代码：{code}").format(code=int(code))
            )
        results["pdf"] = {
            "path": str(pdf_path),
            "size_bytes": pdf_path.stat().st_size,
            "sha256": sha256_file(pdf_path),
        }
    return results


def _inspect_written_project(qgz_path: Path) -> dict[str, object]:
    check_project = QgsProject()
    try:
        read_ok = check_project.read(str(qgz_path))
        layers = list(check_project.mapLayers().values())
        layouts = check_project.layoutManager().layouts()
        item_ids = sorted(
            {
                item.id()
                for layout in layouts
                for item in layout.items()
                if hasattr(item, "id") and item.id()
            }
        )
        return {
            "read_ok": bool(read_ok),
            "layer_count": len(layers),
            "all_layers_valid": all(layer.isValid() for layer in layers),
            "layout_names": [layout.name() for layout in layouts],
            "item_ids": item_ids,
            "variables": check_project.customVariables(),
        }
    finally:
        check_project.clear()


def build_map(
    settings: MapJobSettings,
    plugin_dir: Path,
    source_project: QgsProject | None = None,
    progress: ProgressCallback | None = None,
    is_cancelled: CancelCallback | None = None,
) -> BuildResult:
    """Build a portable, editable thematic-map run without touching inputs."""
    progress = progress or (lambda _value, _message: None)
    is_cancelled = is_cancelled or (lambda: False)
    source_project = source_project or QgsProject.instance()
    errors = validate_settings(settings)
    if errors:
        raise MapBuildError("\n".join(errors))

    plugin_dir = plugin_dir.resolve()
    template_name, template_report_name = _template_names()
    template_path = plugin_dir / "templates" / template_name
    template_report_path = plugin_dir / "templates" / template_report_name
    north_arrow_path = plugin_dir / "assets" / NORTH_ARROW_NAME
    if not template_path.is_file() or not template_report_path.is_file():
        raise MapBuildError(_tr("插件派生QPT或其报告缺失。"))
    if not north_arrow_path.is_file():
        raise MapBuildError(_tr("插件指北针资源缺失。"))
    template_report = json.loads(
        template_report_path.read_text(encoding="utf-8")
    )
    if template_report.get("status") != "PASS":
        raise MapBuildError(_tr("插件派生QPT未通过来源检查。"))
    if sha256_file(template_path) != template_report.get("output_sha256"):
        raise MapBuildError(_tr("插件派生QPT哈希与报告不一致。"))

    run_dir = _make_run_dir(Path(settings.output_root).resolve())
    data_dir = run_dir / "data"
    project_dir = run_dir / "project"
    png_dir = run_dir / "png"
    pdf_dir = run_dir / "pdf"
    qa_dir = run_dir / "qa"
    for directory in (data_dir, qa_dir):
        directory.mkdir(exist_ok=False)
    if settings.export_qgz:
        project_dir.mkdir(exist_ok=False)
    if settings.export_png:
        png_dir.mkdir(exist_ok=False)
    if settings.export_pdf:
        pdf_dir.mkdir(exist_ok=False)

    log_path = run_dir / "run.log"
    _write_text_exclusive(
        log_path,
        _tr("[0] 已创建独立任务目录：{run_dir}\n").format(run_dir=run_dir),
    )

    def emit(value: int, message: str) -> None:
        with log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"[{value}] {message}\n")
        progress(value, message)
        if is_cancelled():
            raise BuildCancelled(_tr("用户取消PS-InSAR专题图生成。"))

    source_files = _existing_source_files(settings, source_project)
    hashes_before = _hash_files(source_files)
    _write_json_exclusive(run_dir / "run_config.json", asdict(settings))
    _write_json_exclusive(
        run_dir / "input_manifest.json",
        {
            "plugin_version": PLUGIN_VERSION,
            "template": str(template_path),
            "template_sha256": sha256_file(template_path),
            "source_files": {
                name: {
                    "path": str(path),
                    "sha256": hashes_before[name],
                    "size_bytes": path.stat().st_size,
                }
                for name, path in source_files.items()
            },
        },
    )

    build_project: QgsProject | None = None
    try:
        emit(5, _tr("只读验证输入图层"))
        source_layer = _load_source_vector(settings, source_project)
        source_feature_count = int(source_layer.featureCount())

        emit(15, _tr("复制垂直形变速率图层到任务目录"))
        vector_copy_path = data_dir / "velocity_grid.gpkg"
        transform_context = source_project.transformContext()
        grid_layer = _copy_vector_layer(
            source_layer,
            vector_copy_path,
            transform_context,
        )
        if grid_layer.featureCount() != source_feature_count:
            raise MapBuildError(_tr("velocity副本要素数与输入不一致。"))

        emit(25, _tr("应用导师确认的velocity分级样式"))
        style = _configure_velocity_style(grid_layer, settings.value_field)

        emit(35, _tr("准备底图"))
        basemap_layer, basemap_metadata = _load_basemap(
            settings,
            source_project,
            data_dir,
        )

        emit(45, _tr("创建独立QGIS工程"))
        build_project = QgsProject()
        build_project.setTitle(settings.title)
        build_project.setBackgroundColor(QColor(255, 255, 255))
        try:
            build_project.setFilePathStorage(Qgis.FilePathType.Relative)
        except (AttributeError, TypeError):
            pass
        build_project.setPresetHomePath(str(run_dir))

        left_lines: list[str] = []
        if settings.show_data_source:
            left_lines.append(
                _tr("数据来源：{value}").format(value=settings.data_source.strip())
            )
        if settings.show_acquisition_time:
            left_lines.append(
                _tr("数据拍摄时间：{value}").format(
                    value=settings.acquisition_time.strip()
                )
            )
        right_lines: list[str] = []
        if settings.show_production_date:
            right_lines.append(
                _tr("制图时间：{value}").format(
                    value=_format_date(settings.production_date)
                )
            )
        if settings.show_production_unit:
            right_lines.append(
                _tr("制作单位：{value}").format(
                    value=settings.production_unit.strip()
                )
            )
        build_project.setCustomVariables(
            {
                "rs_psinsar_plugin_version": PLUGIN_VERSION,
                "velocity_unit": "mm/year",
                "displacement_unit": "mm",
                "positive_direction": "vertical upward",
                "negative_direction": "vertical downward",
                "map_data_source": settings.data_source,
                "map_acquisition_time": settings.acquisition_time,
                "map_production_date": settings.production_date,
                "map_production_unit": settings.production_unit,
                "map_show_data_source": settings.show_data_source,
                "map_show_acquisition_time": (
                    settings.show_acquisition_time
                ),
                "map_show_production_date": settings.show_production_date,
                "map_show_production_unit": settings.show_production_unit,
                "map_metadata_left_text": "\n".join(left_lines),
                "map_metadata_right_text": "\n".join(right_lines),
                "candidate_layer_included": False,
                "subarea_layer_included": False,
                "full_point_layer_included": False,
            }
        )

        if basemap_layer is not None:
            build_project.addMapLayer(basemap_layer)
        build_project.addMapLayer(grid_layer)
        root = build_project.layerTreeRoot()
        root.setHasCustomLayerOrder(True)
        layer_order = [grid_layer]
        if basemap_layer is not None:
            layer_order.append(basemap_layer)
        root.setCustomLayerOrder(layer_order)

        emit(58, _tr("加载派生QPT并绑定图层与动态文本"))
        layout, layout_metadata = _load_and_bind_layout(
            build_project,
            template_path,
            north_arrow_path,
            grid_layer,
            basemap_layer,
            settings,
        )
        referenced_extent = QgsReferencedRectangle(
            layout.itemById("m341_overview_map").extent(),
            build_project.crs(),
        )
        build_project.viewSettings().setPresetFullExtent(referenced_extent)
        build_project.viewSettings().setDefaultViewExtent(referenced_extent)

        emit(68, _tr("导出PNG/PDF"))
        png_path = (
            png_dir / "ps_insar_thematic_map.png"
            if settings.export_png
            else None
        )
        pdf_path = (
            pdf_dir / "ps_insar_thematic_map.pdf"
            if settings.export_pdf
            else None
        )
        export_metadata = _export_layout(
            layout,
            settings,
            png_path,
            pdf_path,
        )

        emit(84, _tr("保存可编辑 QGZ"))
        qgz_path = (
            project_dir / "ps_insar_thematic_map.qgz"
            if settings.export_qgz
            else None
        )
        qgz_inspection: dict[str, object] | None = None
        if qgz_path is not None:
            if not build_project.write(str(qgz_path)):
                raise MapBuildError(_tr("QGIS工程写入失败。"))
            qgz_inspection = _inspect_written_project(qgz_path)

        emit(93, _tr("执行非覆盖和结构验收"))
        hashes_after = _hash_files(source_files)
        expected_width = round(420.0 / 25.4 * settings.dpi)
        expected_height = round(297.0 / 25.4 * settings.dpi)
        checks = {
            "source_feature_count_positive": source_feature_count > 0,
            "copied_feature_count_equal": int(grid_layer.featureCount())
            == source_feature_count,
            "inputs_unchanged": hashes_before == hashes_after,
            "template_hash_matches": sha256_file(template_path)
            == template_report["output_sha256"],
            "dynamic_items_present": all(
                layout.itemById(item_id) is not None
                for item_id in (
                    "plugin_metadata_left",
                    "plugin_metadata_right",
                )
            ),
            "png_written": (
                not settings.export_png
                or (
                    png_path is not None
                    and png_path.is_file()
                    and abs(export_metadata["png"]["width"] - expected_width) <= 3
                    and abs(export_metadata["png"]["height"] - expected_height)
                    <= 3
                )
            ),
            "pdf_written": (
                not settings.export_pdf
                or (
                    pdf_path is not None
                    and pdf_path.is_file()
                    and pdf_path.stat().st_size > 10_000
                )
            ),
            "qgz_written": (
                not settings.export_qgz
                or (
                    qgz_path is not None
                    and qgz_path.is_file()
                    and qgz_inspection is not None
                    and qgz_inspection["read_ok"]
                    and qgz_inspection["all_layers_valid"]
                )
            ),
            "excluded_layers_absent": len(build_project.mapLayers())
            == (2 if basemap_layer is not None else 1),
        }
        status = "PASS" if all(checks.values()) else "REVIEW"
        artifacts = {
            "run_dir": str(run_dir),
            "velocity_copy": str(vector_copy_path),
        }
        if qgz_path is not None:
            artifacts["qgz"] = str(qgz_path)
        if png_path is not None:
            artifacts["png"] = str(png_path)
        if pdf_path is not None:
            artifacts["pdf"] = str(pdf_path)

        report = {
            "status": status,
            "milestone": "M6.2",
            "plugin_version": PLUGIN_VERSION,
            "processing_engine_version": PS_MAP_ENGINE_VERSION,
            "created": datetime.now().isoformat(timespec="seconds"),
            "qgis_version": Qgis.QGIS_VERSION,
            "settings": asdict(settings),
            "semantics": {
                "velocity_unit": "mm/year",
                "displacement_unit": "mm",
                "positive_direction": "vertical upward",
                "negative_direction": "vertical downward",
            },
            "input": {
                "feature_count": source_feature_count,
                "crs": source_layer.crs().authid(),
                "hashes_before": hashes_before,
                "hashes_after": hashes_after,
            },
            "style": style,
            "basemap": basemap_metadata,
            "layout": layout_metadata,
            "exports": export_metadata,
            "qgz_inspection": qgz_inspection,
            "checks": checks,
            "artifacts": artifacts,
        }
        report_path = qa_dir / REPORT_NAME
        _write_json_exclusive(report_path, report)
        emit(100, _tr("PS-InSAR专题图完成：{status}").format(status=status))
        return BuildResult(run_dir, report_path, status, artifacts)
    except BuildCancelled as exc:
        _write_text_exclusive(
            run_dir / "RUN_CANCELLED.md",
            (
                _tr("# PS-InSAR 专题图任务已取消\n\n")
                + _tr("- 插件版本：`{version}`\n").format(version=PLUGIN_VERSION)
                + _tr("- 处理引擎：`{version}`\n\n").format(
                    version=PS_MAP_ENGINE_VERSION
                )
                + f"{exc}\n"
            ),
        )
        raise
    except Exception as exc:
        _write_text_exclusive(
            run_dir / "RUN_FAILED.md",
            "\n".join(
                [
                    _tr("# PS-InSAR 专题图任务失败"),
                    _tr("- 插件版本：`{version}`").format(version=PLUGIN_VERSION),
                    _tr("- 处理引擎：`{version}`").format(
                        version=PS_MAP_ENGINE_VERSION
                    ),
                    "",
                    _tr("错误：{error}").format(error=exc),
                    "",
                    "```text",
                    traceback.format_exc(),
                    "```",
                    "",
                ]
            ),
        )
        raise
    finally:
        if build_project is not None:
            build_project.clear()
