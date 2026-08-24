"""Non-overwriting SAR thematic-map exporter."""

from __future__ import annotations

import hashlib
import json
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
    QgsContrastEnhancement,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsReadWriteContext,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsSingleBandGrayRenderer,
    QgsTextFormat,
    QgsUnitTypes,
)

from .localization import language_code, tr
from .sar_core import inspect_raster, sampled_percentiles
from .sar_map_settings import (
    SAR_MAP_VERSION,
    SarMapSettings,
    compose_production_panel,
    compose_right_panel,
    compose_source_panel,
    validate_sar_map_settings,
)


TEMPLATE_NAME_ZH = "backscatter_template_v1.qpt"
TEMPLATE_REPORT_NAME_ZH = "backscatter_template_v1_report.json"
TEMPLATE_NAME_EN = "backscatter_template_v1_en.qpt"
TEMPLATE_REPORT_NAME_EN = "backscatter_template_v1_en_report.json"
COLORBAR_ASSET_NAME = "sar_gray_colorbar.svg"
TRANSLATION_CONTEXT = "@default"
LAYOUT_NAME = "SAR 强度 dB 专题图（可编辑）"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


def _template_names() -> tuple[str, str]:
    """Select only the presentation template; processing contracts stay shared."""
    if language_code() == "en":
        return TEMPLATE_NAME_EN, TEMPLATE_REPORT_NAME_EN
    return TEMPLATE_NAME_ZH, TEMPLATE_REPORT_NAME_ZH


class SarMapBuildError(RuntimeError):
    """Raised when a SAR map cannot satisfy an acceptance gate."""


@dataclass(frozen=True)
class SarMapBuildResult:
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


def _write_json_exclusive(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")


def _write_text_exclusive(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def _make_run_dir(output_root: Path) -> Path:
    stem = datetime.now().strftime("%Y%m%dT%H%M%S") + "_sar_map"
    candidate = output_root / stem
    counter = 1
    while candidate.exists():
        candidate = output_root / f"{stem}_{counter:02d}"
        counter += 1
    candidate.mkdir(parents=False, exist_ok=False)
    return candidate


def _format_production_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    if language_code() == "en":
        return parsed.isoformat()
    return f"{parsed.year}年{parsed.month}月{parsed.day}日"


def _layout_item(layout: QgsPrintLayout, item_id: str, expected_type):
    item = layout.itemById(item_id)
    if item is None or not isinstance(item, expected_type):
        raise SarMapBuildError(
            _tr("SAR 模板缺少布局项：{item_id}").format(
                item_id=item_id
            )
        )
    return item


def _fill_extent_to_ratio(
    extent: QgsRectangle,
    target_ratio: float,
) -> QgsRectangle:
    result = QgsRectangle(extent)
    if result.isEmpty() or target_ratio <= 0:
        return result
    current_ratio = result.width() / result.height()
    center_x = result.center().x()
    center_y = result.center().y()
    if current_ratio < target_ratio:
        half_height = result.width() / target_ratio / 2.0
        result.setYMinimum(center_y - half_height)
        result.setYMaximum(center_y + half_height)
    elif current_ratio > target_ratio:
        half_width = result.height() * target_ratio / 2.0
        result.setXMinimum(center_x - half_width)
        result.setXMaximum(center_x + half_width)
    return result


def _configure_gray_style(
    layer: QgsRasterLayer,
    minimum: float,
    maximum: float,
) -> None:
    provider = layer.dataProvider()
    renderer = QgsSingleBandGrayRenderer(provider, 1)
    renderer.setGradient(QgsSingleBandGrayRenderer.BlackToWhite)
    enhancement = QgsContrastEnhancement(provider.dataType(1))
    enhancement.setMinimumValue(minimum)
    enhancement.setMaximumValue(maximum)
    enhancement.setContrastEnhancementAlgorithm(
        QgsContrastEnhancement.StretchToMinimumMaximum
    )
    renderer.setContrastEnhancement(enhancement)
    layer.setRenderer(renderer)
    layer.setCustomProperty("rs_psinsar/display_min_db", minimum)
    layer.setCustomProperty("rs_psinsar/display_max_db", maximum)
    layer.setCustomProperty(
        "rs_psinsar/display_style",
        "black_to_white_2_98_percentile",
    )
    layer.triggerRepaint()


def _load_layout(
    project: QgsProject,
    template_path: Path,
    colorbar_path: Path,
    raster_layer: QgsRasterLayer,
    settings: SarMapSettings,
    display_min: float,
    display_max: float,
) -> tuple[QgsPrintLayout, dict[str, object]]:
    document = QDomDocument()
    ok, message, line, column = document.setContent(
        template_path.read_text(encoding="utf-8")
    )
    if not ok:
        raise SarMapBuildError(
            _tr("SAR QPT XML 错误 {line}:{column}：{message}").format(
                line=line,
                column=column,
                message=message,
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
        raise SarMapBuildError(_tr("QGIS 无法加载 SAR 专题图模板。"))
    layout.setName(_tr("SAR 强度 dB 专题图（可编辑）"))

    title = _layout_item(layout, "title", QgsLayoutItemLabel)
    map_item = _layout_item(layout, "main_map", QgsLayoutItemMap)
    legend = _layout_item(
        layout,
        "continuous_legend",
        QgsLayoutItemLegend,
    )
    scale = _layout_item(layout, "scale_bar", QgsLayoutItemScaleBar)
    _layout_item(layout, "north_arrow", QgsLayoutItemPicture)
    legend_heading = _layout_item(
        layout,
        "legend_heading",
        QgsLayoutItemLabel,
    )
    legend_unit = _layout_item(
        layout,
        "legend_unit",
        QgsLayoutItemLabel,
    )
    right_panel = _layout_item(layout, "crs_note", QgsLayoutItemLabel)
    source_panel = _layout_item(layout, "source_note", QgsLayoutItemLabel)
    production_panel = _layout_item(
        layout,
        "production_note",
        QgsLayoutItemLabel,
    )

    title.setText(settings.title.strip())
    legend_heading.setText(_tr("VV 极化 SAR 强度"))
    legend_unit.setText(_tr("单位：dB"))

    project.setCrs(raster_layer.crs())
    map_item.setCrs(raster_layer.crs())
    map_item.setLayers([raster_layer])
    map_item.setKeepLayerSet(True)
    map_item.setBackgroundEnabled(True)
    map_item.setBackgroundColor(QColor(255, 255, 255))
    target_ratio = map_item.rect().width() / map_item.rect().height()
    map_extent = _fill_extent_to_ratio(
        raster_layer.extent(),
        target_ratio,
    )
    map_item.setExtent(map_extent)

    # QGIS' automatic raster legend adds a band heading and exposes raw
    # floating-point values.  Keep the template item (so an operator can
    # restore it manually) but replace it with three independent, editable
    # layout items whose wording and precision are deterministic.
    legend.setVisibility(False)
    legend.setExcludeFromExports(True)
    legend_position = legend.positionWithUnits()
    legend_size = legend.sizeWithUnits()
    colorbar_x = legend_position.x() + 2.0
    colorbar_y = legend_position.y() + 12.0
    colorbar_width = 18.0
    colorbar_height = max(60.0, min(99.99, legend_size.height() - 24.0))

    colorbar = QgsLayoutItemPicture(layout)
    colorbar.setId("legend_colorbar")
    colorbar.setResizeMode(QgsLayoutItemPicture.Stretch)
    colorbar.setPicturePath(str(colorbar_path))
    colorbar.attemptMove(
        QgsLayoutPoint(
            colorbar_x,
            colorbar_y,
            QgsUnitTypes.LayoutMillimeters,
        )
    )
    colorbar.attemptResize(
        QgsLayoutSize(
            colorbar_width,
            colorbar_height,
            QgsUnitTypes.LayoutMillimeters,
        )
    )
    layout.addLayoutItem(colorbar)

    number_format = QgsTextFormat()
    number_font = QFont("Times New Roman")
    number_font.setPointSizeF(24.0)
    number_format.setFont(number_font)
    number_format.setSize(24.0)
    number_format.setColor(QColor(0, 0, 0))
    if hasattr(number_format, "setFallbackFamilies"):
        number_format.setFallbackFamilies(["Times New Roman", "SimSun", "宋体"])

    label_x = colorbar_x + colorbar_width + 2.5
    label_width = max(22.0, legend_size.width() - colorbar_width - 6.5)

    def add_number_label(
        item_id: str,
        value: float,
        y_position: float,
    ) -> QgsLayoutItemLabel:
        label = QgsLayoutItemLabel(layout)
        label.setId(item_id)
        label.setText(f"{value:.2f} dB")
        label.setTextFormat(number_format)
        label.setHAlign(Qt.AlignLeft)
        label.setVAlign(Qt.AlignVCenter)
        label.attemptMove(
            QgsLayoutPoint(
                label_x,
                y_position,
                QgsUnitTypes.LayoutMillimeters,
            )
        )
        label.attemptResize(
            QgsLayoutSize(
                label_width,
                10.0,
                QgsUnitTypes.LayoutMillimeters,
            )
        )
        layout.addLayoutItem(label)
        return label

    add_number_label(
        "legend_max_label",
        display_max,
        colorbar_y - 3.0,
    )
    add_number_label(
        "legend_min_label",
        display_min,
        colorbar_y + colorbar_height - 5.0,
    )
    scale.setLinkedMap(map_item)
    scale.refresh()
    if scale.sizeWithUnits().width() > 100.0:
        scale.setSegmentSizeMode(Qgis.ScaleBarSegmentSizeMode.FitWidth)
        scale.setMinimumBarWidth(50.0)
        scale.setMaximumBarWidth(100.0)
        scale.refresh()

    right_text = compose_right_panel(settings)
    source_text = compose_source_panel(settings)
    production_text = compose_production_panel(
        settings,
        _format_chinese_date(settings.production_date)
        if settings.show_production_date
        else "",
    )
    panels = (
        (right_panel, right_text),
        (source_panel, source_text),
        (production_panel, production_text),
    )
    for label, text in panels:
        label.setText(text)
        label.setVisibility(bool(text))
        label.refresh()

    project.layoutManager().addLayout(layout)
    return layout, {
        "layout_name": layout.name(),
        "map_crs": raster_layer.crs().authid(),
        "map_extent": [
            map_extent.xMinimum(),
            map_extent.yMinimum(),
            map_extent.xMaximum(),
            map_extent.yMaximum(),
        ],
        "display_min_db": display_min,
        "display_max_db": display_max,
        "legend_mode": "independent_editable_gray_colorbar",
        "legend_max_label": f"{display_max:.2f} dB",
        "legend_min_label": f"{display_min:.2f} dB",
        "automatic_raster_legend_visible": False,
        "right_panel_text": right_text,
        "source_panel_text": source_text,
        "production_panel_text": production_text,
        "required_item_ids": [
            "title",
            "main_map",
            "continuous_legend",
            "legend_colorbar",
            "legend_max_label",
            "legend_min_label",
            "scale_bar",
            "north_arrow",
            "legend_heading",
            "legend_unit",
            "crs_note",
            "source_note",
            "production_note",
        ],
    }


def _export_layout(
    layout: QgsPrintLayout,
    settings: SarMapSettings,
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
            raise SarMapBuildError(
                _tr("PNG 导出失败，QGIS 代码：{code}").format(
                    code=int(code)
                )
            )
        image = QImage(str(png_path))
        if image.isNull():
            raise SarMapBuildError(_tr("PNG 导出后无法重新读取。"))
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
            raise SarMapBuildError(
                _tr("PDF 导出失败，QGIS 代码：{code}").format(
                    code=int(code)
                )
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
        layout_items: dict[str, dict[str, object]] = {}
        for layout in layouts:
            for item in layout.items():
                if not hasattr(item, "id") or not item.id():
                    continue
                record: dict[str, object] = {
                    "visible": bool(item.isVisible()),
                    "type": type(item).__name__,
                }
                if isinstance(item, QgsLayoutItemLabel):
                    record["text"] = item.text()
                if isinstance(item, QgsLayoutItemPicture):
                    record["picture_path"] = item.picturePath()
                    record["picture_missing"] = bool(item.isMissingImage())
                layout_items[item.id()] = record
        return {
            "read_ok": bool(read_ok),
            "layer_count": len(layers),
            "all_layers_valid": all(layer.isValid() for layer in layers),
            "layout_names": [layout.name() for layout in layouts],
            "item_ids": sorted(layout_items),
            "layout_items": layout_items,
        }
    finally:
        check_project.clear()


def _render_markdown(report: dict[str, object]) -> str:
    layout = report["layout"]
    return (
        _tr("# SAR 强度 dB 专题图导出报告\n\n")
        + _tr("- 状态：`{status}`\n").format(status=report["status"])
        + _tr("- 插件版本：`{version}`\n").format(
            version=report["plugin_version"]
        )
        + _tr("- 输入：`{path}`\n").format(path=report["input"]["path"])
        + _tr("- 输入 SHA-256：`{value}`\n").format(
            value=report["input"]["sha256_before"]
        )
        + _tr("- 模板 SHA-256：`{value}`\n").format(
            value=report["template"]["sha256"]
        )
        + _tr("- 坐标参考系：`{crs}`\n").format(crs=layout["map_crs"])
        + _tr("- 显示范围：`{minimum:.6f}` 至 `{maximum:.6f}` dB\n").format(
            minimum=layout["display_min_db"],
            maximum=layout["display_max_db"],
        )
        + _tr("- 显示方式：2%—98% 分位数，黑—白线性拉伸\n")
        + _tr("- 原始 dB 栅格未重算，输入文件哈希在导出前后保持一致。\n")
        + _tr("- QGZ 为正式可编辑成果；PNG/PDF 为本次导出快照。\n")
    )


def build_sar_map(
    settings: SarMapSettings,
    plugin_dir: Path,
    progress: ProgressCallback | None = None,
    is_cancelled: CancelCallback | None = None,
) -> SarMapBuildResult:
    """Build a new editable SAR map run without changing the source raster."""
    progress = progress or (lambda _value, _message: None)
    is_cancelled = is_cancelled or (lambda: False)
    errors = validate_sar_map_settings(settings)
    if errors:
        raise SarMapBuildError("\n".join(errors))

    plugin_dir = plugin_dir.resolve()
    template_name, template_report_name = _template_names()
    template_path = plugin_dir / "templates" / template_name
    template_report_path = plugin_dir / "templates" / template_report_name
    colorbar_asset_path = plugin_dir / "assets" / COLORBAR_ASSET_NAME
    if not template_path.is_file() or not template_report_path.is_file():
        raise SarMapBuildError(_tr("SAR 专题图模板或来源报告缺失。"))
    if not colorbar_asset_path.is_file():
        raise SarMapBuildError(_tr("SAR 灰度色标资源缺失。"))
    template_report = json.loads(
        template_report_path.read_text(encoding="utf-8")
    )
    if template_report.get("status") != "PASS":
        raise SarMapBuildError(_tr("SAR 专题图模板未通过来源审查。"))
    template_hash = sha256_file(template_path)
    if template_hash != template_report.get("output_qpt_sha256"):
        raise SarMapBuildError(
            _tr("SAR 专题图模板哈希与来源报告不一致。")
        )

    source_path = Path(settings.raster_path).resolve()
    source_hash_before = sha256_file(source_path)
    source_info = inspect_raster(source_path)
    if source_info["band_count"] != 1:
        raise SarMapBuildError(_tr("SAR 专题图输入必须是单波段栅格。"))
    if not source_info["crs"]:
        raise SarMapBuildError(
            _tr("SAR 专题图输入缺少有效坐标参考系。")
        )

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
        f"[0] {SAR_MAP_VERSION} run created: {run_dir}\n",
    )

    def emit(value: int, message: str) -> None:
        with log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"[{value}] {message}\n")
        progress(value, message)
        if is_cancelled():
            raise SarMapBuildError(_tr("用户取消了 SAR 专题图导出。"))

    _write_json_exclusive(run_dir / "run_config.json", asdict(settings))
    _write_json_exclusive(
        run_dir / "input_manifest.json",
        {
            "plugin_version": SAR_MAP_VERSION,
            "source": {
                "path": str(source_path),
                "sha256": source_hash_before,
                "size_bytes": source_path.stat().st_size,
            },
            "template": {
                "path": str(template_path),
                "sha256": template_hash,
            },
            "colorbar_asset": {
                "path": str(colorbar_asset_path),
                "sha256": sha256_file(colorbar_asset_path),
            },
        },
    )

    build_project: QgsProject | None = None
    try:
        emit(10, _tr("复制 dB 栅格到新的便携式 run"))
        copied_raster = data_dir / "sar_backscatter_db.tif"
        shutil.copy2(source_path, copied_raster)
        if sha256_file(copied_raster) != source_hash_before:
            raise SarMapBuildError(
                _tr("dB 栅格副本哈希与输入不一致。")
            )
        copied_colorbar = data_dir / COLORBAR_ASSET_NAME
        shutil.copy2(colorbar_asset_path, copied_colorbar)

        emit(25, _tr("计算 2%—98% 显示分位数"))
        display_min, display_max = sampled_percentiles(
            copied_raster,
            2.0,
            98.0,
        )

        emit(40, _tr("创建独立 QGIS 工程和灰度渲染"))
        build_project = QgsProject()
        build_project.setTitle(settings.title)
        build_project.setBackgroundColor(QColor(255, 255, 255))
        try:
            build_project.setFilePathStorage(Qgis.FilePathType.Relative)
        except (AttributeError, TypeError):
            pass
        build_project.setPresetHomePath(str(run_dir))

        raster_layer = QgsRasterLayer(
            str(copied_raster),
            _tr("BC2 VV SAR 强度（dB）"),
            "gdal",
        )
        if not raster_layer.isValid():
            raise SarMapBuildError(_tr("QGIS 无法加载 dB 栅格副本。"))
        _configure_gray_style(raster_layer, display_min, display_max)
        build_project.addMapLayer(raster_layer)

        right_text = compose_right_panel(settings)
        source_text = compose_source_panel(settings)
        production_text = compose_production_panel(
            settings,
            _format_production_date(settings.production_date)
            if settings.show_production_date
            else "",
        )
        build_project.setCustomVariables(
            {
                "rs_psinsar_plugin_version": SAR_MAP_VERSION,
                "sar_input_semantics": "dB",
                "sar_display_low_percentile": 2.0,
                "sar_display_high_percentile": 98.0,
                "sar_display_min_db": display_min,
                "sar_display_max_db": display_max,
                "map_show_crs": settings.show_crs,
                "map_show_resolution": settings.show_resolution,
                "map_show_display_method": settings.show_display_method,
                "map_show_data_source": settings.show_data_source,
                "map_show_acquisition_time": settings.show_acquisition_time,
                "map_show_production_date": settings.show_production_date,
                "map_show_production_unit": settings.show_production_unit,
                "map_right_panel_text": right_text,
                "map_source_panel_text": source_text,
                "map_production_panel_text": production_text,
            }
        )

        emit(55, _tr("绑定 SAR 强度专题图模板和七项可选信息"))
        layout, layout_metadata = _load_layout(
            build_project,
            template_path,
            copied_colorbar,
            raster_layer,
            settings,
            display_min,
            display_max,
        )
        main_map = layout.itemById("main_map")
        if not isinstance(main_map, QgsLayoutItemMap):
            raise SarMapBuildError(
                _tr("SAR 专题图布局缺少主地图范围。")
            )
        referenced_extent = QgsReferencedRectangle(
            main_map.extent(),
            build_project.crs(),
        )
        build_project.viewSettings().setPresetFullExtent(referenced_extent)
        build_project.viewSettings().setDefaultViewExtent(referenced_extent)

        artifacts: dict[str, str] = {}
        qgz_path: Path | None = None
        if settings.export_qgz:
            emit(65, _tr("保存可人工微调的 QGZ"))
            qgz_path = project_dir / "sar_backscatter_map.qgz"
            build_project.setFileName(str(qgz_path))
            if not build_project.write():
                raise SarMapBuildError(_tr("QGZ 保存失败。"))
            artifacts["qgz"] = str(qgz_path)

        emit(75, _tr("导出 PNG/PDF"))
        png_path = (
            png_dir / "sar_backscatter_map.png"
            if settings.export_png
            else None
        )
        pdf_path = (
            pdf_dir / "sar_backscatter_map.pdf"
            if settings.export_pdf
            else None
        )
        export_metadata = _export_layout(
            layout,
            settings,
            png_path,
            pdf_path,
        )
        if png_path is not None:
            artifacts["png"] = str(png_path)
        if pdf_path is not None:
            artifacts["pdf"] = str(pdf_path)

        emit(90, _tr("执行输入完整性与工程结构复核"))
        source_hash_after = sha256_file(source_path)
        if source_hash_after != source_hash_before:
            raise SarMapBuildError(
                _tr("输入 dB 栅格在制图前后哈希发生变化。")
            )
        project_inspection = (
            _inspect_written_project(qgz_path)
            if qgz_path is not None
            else None
        )
        if project_inspection is not None and (
            not project_inspection["read_ok"]
            or not project_inspection["all_layers_valid"]
        ):
            raise SarMapBuildError(
                _tr("写出的 QGZ 重新读取检查未通过。")
            )
        if project_inspection is not None:
            inspected_items = project_inspection["layout_items"]
            colorbar_inspection = inspected_items.get(
                "legend_colorbar",
                {},
            )
            if (
                "legend_colorbar" not in inspected_items
                or colorbar_inspection.get("picture_missing", True)
            ):
                raise SarMapBuildError(
                    _tr("写出的 QGZ 缺少可用的独立灰度色标资源。")
                )

        report: dict[str, object] = {
            "status": "PASS",
            "plugin_version": SAR_MAP_VERSION,
            "run_dir": str(run_dir),
            "input": {
                "path": str(source_path),
                "sha256_before": source_hash_before,
                "sha256_after": source_hash_after,
                "preserved": source_hash_before == source_hash_after,
                "inspection": source_info,
            },
            "template": {
                "path": str(template_path),
                "sha256": template_hash,
                "source_qgz_sha256": template_report.get(
                    "source_qgz_sha256"
                ),
                "source_qpt_sha256": template_report.get(
                    "source_qpt_sha256"
                ),
            },
            "layout": layout_metadata,
            "exports": export_metadata,
            "project_inspection": project_inspection,
            "artifacts": artifacts,
            "processing_boundary": {
                "mosaic_recomputed": False,
                "clip_recomputed": False,
                "db_conversion_recomputed": False,
                "display_only": True,
            },
        }
        report_path = qa_dir / "sar_map_report.json"
        _write_json_exclusive(report_path, report)
        _write_text_exclusive(
            qa_dir / "sar_map_report.md",
            _render_markdown(report),
        )
        artifacts["report_json"] = str(report_path)
        artifacts["report_md"] = str(qa_dir / "sar_map_report.md")
        emit(100, _tr("SAR 强度 dB 专题图导出完成：PASS"))
        return SarMapBuildResult(
            run_dir=run_dir,
            report_path=report_path,
            status="PASS",
            artifacts=artifacts,
        )
    except Exception as exc:
        failure = (
            _tr("# SAR 专题图导出失败\n\n")
            + _tr("- 错误类型：`{error_type}`\n").format(
                error_type=type(exc).__name__
            )
            + _tr("- 错误信息：{error}\n\n").format(error=exc)
            + _tr("本次任务目录保留用于诊断；输入 dB 栅格和模板未被覆盖。\n\n")
            + "```text\n"
            + traceback.format_exc()
            + "```\n"
        )
        failure_path = run_dir / "RUN_FAILED.md"
        if not failure_path.exists():
            _write_text_exclusive(failure_path, failure)
        raise
    finally:
        if build_project is not None:
            build_project.clear()
