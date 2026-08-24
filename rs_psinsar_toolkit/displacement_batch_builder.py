"""QGIS project/layout/export workflow for cumulative-displacement batches."""

from __future__ import annotations

import gc
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from qgis.PyQt.QtGui import QColor, QImage
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
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
    QgsVectorLayer,
)

from .localization import language_code, tr
from .displacement_batch_core import (
    BatchCancelled,
    BatchCoreError,
    GridBuildResult,
    build_cumulative_grid,
)
from .displacement_batch_settings import (
    BATCH_ENGINE_VERSION,
    BatchMapSettings,
    validate_batch_settings,
)
from .tasking import RunContext, TaskSpec


ProgressCallback = Callable[[int, str], None]
CancelCallback = Callable[[], bool]
TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)


def _bundled_template_path(plugin_dir: Path) -> Path:
    name = (
        "cumulative_displacement_template_v1_en.qpt"
        if language_code() == "en"
        else "cumulative_displacement_template_v1.qpt"
    )
    return plugin_dir / "templates" / name

CLASS_COLORS = (
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
)
CLASS_EDGES = (
    -1.0e30,
    -20.0,
    -15.0,
    -10.0,
    -5.0,
    -2.0,
    0.0,
    2.0,
    5.0,
    10.0,
    15.0,
    20.0,
    1.0e30,
)
CLASS_LABELS = (
    "≤ −20",
    "−20 – −15",
    "−15 – −10",
    "−10 – \u2007−5",
    "\u2007−5 – \u2007−2",
    "\u2007−2 – \u2007\u20070",
    "\u2007\u20070 – \u2007\u20072",
    "\u2007\u20072 – \u2007\u20075",
    "\u2007\u20075 – \u200710",
    "\u200710 – \u200715",
    "\u200715 – \u200720",
    "≥ \u200720",
)


@dataclass(frozen=True)
class BatchBuildResult:
    run_dir: Path
    status: str
    qgz_path: Path | None
    grid_gpkg: Path
    period_count: int
    png_count: int
    pdf_count: int
    report_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _load_document(path: Path) -> QDomDocument:
    document = QDomDocument()
    ok, message, line, column = document.setContent(
        path.read_text(encoding="utf-8")
    )
    if not ok:
        raise BatchCoreError(
            _tr("QPT XML错误 {line}:{column}：{message}").format(
                line=line, column=column, message=message
            )
        )
    return document


def _item(layout: QgsPrintLayout, item_id: str, item_type):
    result = layout.itemById(item_id)
    if result is None or not isinstance(result, item_type):
        raise BatchCoreError(
            _tr("模板缺少布局项目：{item_id}").format(item_id=item_id)
        )
    return result


def _style_grid(layer: QgsVectorLayer, field_name: str) -> None:
    ranges: list[QgsRendererRange] = []
    for lower, upper, color, label in zip(
        CLASS_EDGES[:-1],
        CLASS_EDGES[1:],
        CLASS_COLORS,
        CLASS_LABELS,
    ):
        symbol = QgsFillSymbol.createSimple(
            {"color": color, "outline_style": "no"}
        )
        symbol.setOpacity(0.72)
        ranges.append(QgsRendererRange(lower, upper, symbol, label))
    layer.setRenderer(QgsGraduatedSymbolRenderer(field_name, ranges))
    layer.setCustomProperty("m722/formula", "D_target - D_initial")
    layer.setCustomProperty("m722/unit", "mm")
    layer.setCustomProperty("m722/grid_aggregation", "median")
    layer.setCustomProperty("m722/extreme_points_included", False)


def _set_metadata(
    layout: QgsPrintLayout,
    settings: BatchMapSettings,
    initial_date: str,
    target_date: str,
) -> None:
    left = _item(layout, "plugin_metadata_left", QgsLayoutItemLabel)
    left_lines: list[str] = []
    if settings.show_data_source:
        left_lines.append(_tr("数据来源：{value}").format(value=settings.data_source))
    if settings.show_monitoring_period:
        left_lines.append(
            _tr("监测时段：{initial_date}—{target_date}").format(
                initial_date=initial_date, target_date=target_date
            )
        )
    left.setText("\n".join(left_lines))
    left.setVisibility(bool(left_lines))

    right = _item(layout, "plugin_metadata_right", QgsLayoutItemLabel)
    right_lines: list[str] = []
    if settings.show_production_date:
        right_lines.append(
            _tr("制图时间：{value}").format(value=settings.production_date)
        )
    if settings.show_production_unit:
        right_lines.append(
            _tr("制作单位：{value}").format(value=settings.production_unit)
        )
    right.setText("\n".join(right_lines))
    right.setVisibility(bool(right_lines))


def _build_layout(
    project: QgsProject,
    template_path: Path,
    layer: QgsVectorLayer,
    basemap: QgsRasterLayer,
    north_arrow: Path,
    settings: BatchMapSettings,
    initial_date: str,
    target_date: str,
) -> QgsPrintLayout:
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    _, ok = layout.loadFromTemplate(
        _load_document(template_path),
        QgsReadWriteContext(),
        True,
    )
    if not ok:
        raise BatchCoreError(_tr("QGIS无法加载累计形变QPT模板。"))
    layout.setName(
        _tr("累计垂直形变量_{target_date}").format(target_date=target_date)
    )
    title = _item(layout, "m341_title", QgsLayoutItemLabel)
    title.setText(
        settings.title_pattern.format(
            initial_date=initial_date,
            target_date=target_date,
        )
    )
    map_item = _item(layout, "m341_overview_map", QgsLayoutItemMap)
    map_item.setLayers([layer, basemap])
    map_item.setKeepLayerSet(True)
    map_item.setBackgroundEnabled(True)
    map_item.setBackgroundColor(QColor(255, 255, 255))

    legend = _item(
        layout,
        "m341_velocity_legend",
        QgsLayoutItemLegend,
    )
    legend.setLinkedMap(map_item)
    legend.setAutoUpdateModel(False)
    legend.model().rootGroup().removeAllChildren()
    node = legend.model().rootGroup().addLayer(layer)
    node.setCustomProperty("legend/title-label", " ")
    legend.setTitle("")
    legend.setResizeToContents(True)
    legend.refresh()

    scale = _item(layout, "m341_scale_bar", QgsLayoutItemScaleBar)
    scale.setLinkedMap(map_item)
    north = _item(layout, "m341_north_arrow", QgsLayoutItemPicture)
    north.setPicturePath(str(north_arrow))
    _set_metadata(
        layout,
        settings,
        initial_date,
        target_date,
    )
    project.layoutManager().addLayout(layout)
    return layout


def _export_layout(
    layout: QgsPrintLayout,
    *,
    png_path: Path | None,
    pdf_path: Path | None,
    dpi: int,
) -> dict[str, Any]:
    exporter = QgsLayoutExporter(layout)
    result: dict[str, Any] = {}
    if png_path is not None:
        image_settings = QgsLayoutExporter.ImageExportSettings()
        image_settings.dpi = dpi
        code = exporter.exportToImage(str(png_path), image_settings)
        if code != QgsLayoutExporter.Success:
            raise BatchCoreError(
                _tr("PNG导出失败：{code}").format(code=int(code))
            )
        image = QImage(str(png_path))
        if image.isNull():
            raise BatchCoreError(
                _tr("PNG无法重新读取：{path}").format(path=png_path)
            )
        result["png"] = {
            "path": str(png_path),
            "width": image.width(),
            "height": image.height(),
            "size": png_path.stat().st_size,
            "sha256": _sha256(png_path),
        }
    if pdf_path is not None:
        pdf_settings = QgsLayoutExporter.PdfExportSettings()
        code = exporter.exportToPdf(str(pdf_path), pdf_settings)
        if code != QgsLayoutExporter.Success:
            raise BatchCoreError(
                _tr("PDF导出失败：{code}").format(code=int(code))
            )
        result["pdf"] = {
            "path": str(pdf_path),
            "size": pdf_path.stat().st_size,
            "sha256": _sha256(pdf_path),
        }
    return result


def _inspect_project(path: Path, expected_periods: int) -> dict[str, Any]:
    check = QgsProject()
    try:
        read_ok = check.read(str(path))
        layouts = check.layoutManager().printLayouts()
        layers = list(check.mapLayers().values())
        return {
            "read_ok": read_ok,
            "layout_count": len(layouts),
            "expected_layout_count": expected_periods,
            "layer_count": len(layers),
            "all_layers_valid": bool(layers)
            and all(layer.isValid() for layer in layers),
            "layout_names": [layout.name() for layout in layouts],
        }
    finally:
        check.clear()


def _render_project_and_maps(
    settings: BatchMapSettings,
    plugin_dir: Path,
    context: RunContext,
    grid_result: GridBuildResult,
    *,
    progress: ProgressCallback,
    is_cancelled: CancelCallback,
) -> dict[str, Any]:
    run_dir = context.run_dir
    project_dir = run_dir / "project"
    png_dir = run_dir / "maps" / "png"
    pdf_dir = run_dir / "maps" / "pdf"
    template_dir = run_dir / "template"
    assets_dir = run_dir / "assets"
    periods_dir = run_dir / "qa" / "periods"
    for directory in (
        project_dir,
        png_dir,
        pdf_dir,
        template_dir,
        assets_dir,
        periods_dir,
    ):
        directory.mkdir(parents=True, exist_ok=False)

    source_template = (
        Path(settings.template_path).resolve()
        if settings.template_path.strip()
        else _bundled_template_path(plugin_dir)
    )
    copied_template = template_dir / source_template.name
    copied_basemap = run_dir / "data" / "basemap.tif"
    copied_north = assets_dir / "north_arrow_simple.svg"
    shutil.copy2(source_template, copied_template)
    shutil.copy2(Path(settings.basemap_path).resolve(), copied_basemap)
    shutil.copy2(
        plugin_dir / "assets" / "north_arrow_simple.svg",
        copied_north,
    )
    input_copy_hashes = {
        "template_source": _sha256(source_template),
        "template_copy": _sha256(copied_template),
        "basemap_source": _sha256(Path(settings.basemap_path).resolve()),
        "basemap_copy": _sha256(copied_basemap),
    }
    if (
        input_copy_hashes["template_source"]
        != input_copy_hashes["template_copy"]
        or input_copy_hashes["basemap_source"]
        != input_copy_hashes["basemap_copy"]
    ):
        raise BatchCoreError(_tr("模板或底图副本哈希不一致。"))

    project = QgsProject()
    try:
        project.setTitle(_tr("PS-InSAR累计垂直形变量批量专题图"))
        project.setBackgroundColor(QColor(255, 255, 255))
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        try:
            project.setFilePathStorage(Qgis.FilePathType.Relative)
        except (AttributeError, TypeError):
            pass
        project.setPresetHomePath(str(run_dir))
        project.setCustomVariables(
            {
                "m722_status": "BATCH_OUTPUT",
                "formula": "D_target - D_initial",
                "initial_field": grid_result.initial_field,
                "initial_date": grid_result.initial_date,
                "displacement_unit": "mm",
                "positive_direction": "vertical upward",
                "negative_direction": "vertical downward",
                "grid_size_m": 50.0,
                "display_minimum_mm": -20.0,
                "display_maximum_mm": 20.0,
                "display_minimum_m": -20.0,
                "display_maximum_m": 20.0,
                "extreme_point_layer_included": False,
            }
        )
        basemap_layer = QgsRasterLayer(
            str(copied_basemap),
            _tr("卫星影像底图"),
            "gdal",
        )
        if not basemap_layer.isValid():
            raise BatchCoreError(_tr("QGIS无法加载底图副本。"))
        project.addMapLayer(basemap_layer)

        period_layers: dict[str, QgsVectorLayer] = {}
        for period in grid_result.periods:
            layer = QgsVectorLayer(
                f"{grid_result.output_gpkg}|"
                "layername=cumulative_displacement_grid_50m",
                _tr("{date} 50米中位数累计形变量（mm）").format(
                    date=period.acquisition_date
                ),
                "ogr",
            )
            if not layer.isValid():
                raise BatchCoreError(
                    _tr("QGIS无法加载累计形变网格：{field}").format(
                        field=period.source_field
                    )
                )
            _style_grid(layer, period.output_field)
            project.addMapLayer(layer)
            period_layers[period.source_field] = layer

        root = project.layerTreeRoot()
        for layer in project.mapLayers().values():
            node = root.findLayer(layer.id())
            if node is not None:
                node.setItemVisibilityChecked(False)
        root.findLayer(basemap_layer.id()).setItemVisibilityChecked(True)
        first_layer = period_layers[grid_result.periods[0].source_field]
        root.findLayer(first_layer.id()).setItemVisibilityChecked(True)
        root.setHasCustomLayerOrder(True)
        root.setCustomLayerOrder(
            [
                period_layers[item.source_field]
                for item in grid_result.periods
            ]
            + [basemap_layer]
        )

        exports: dict[str, Any] = {}
        layouts: list[dict[str, Any]] = []
        total = len(grid_result.periods)
        for index, period in enumerate(grid_result.periods, start=1):
            if is_cancelled():
                raise BatchCancelled(_tr("用户在专题图导出阶段取消任务。"))
            layer = period_layers[period.source_field]
            layout = _build_layout(
                project,
                copied_template,
                layer,
                basemap_layer,
                copied_north,
                settings,
                grid_result.initial_date,
                period.acquisition_date,
            )
            key = period.acquisition_date.replace("-", "")
            png_path = (
                png_dir / f"cumulative_displacement_{key}.png"
                if settings.export_png
                else None
            )
            pdf_path = (
                pdf_dir / f"cumulative_displacement_{key}.pdf"
                if settings.export_pdf
                else None
            )
            exports[period.source_field] = _export_layout(
                layout,
                png_path=png_path,
                pdf_path=pdf_path,
                dpi=settings.dpi,
            )
            map_item = _item(
                layout,
                "m341_overview_map",
                QgsLayoutItemMap,
            )
            period_status = {
                "status": "PASS",
                "ordinal": index,
                "source_field": period.source_field,
                "target_date": period.acquisition_date,
                "output_field": period.output_field,
                "exports": exports[period.source_field],
            }
            (periods_dir / f"{index:02d}_{key}_pass.json").write_text(
                json.dumps(period_status, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            layouts.append(
                {
                    "name": layout.name(),
                    "target_date": period.acquisition_date,
                    "map_extent": [
                        map_item.extent().xMinimum(),
                        map_item.extent().yMinimum(),
                        map_item.extent().xMaximum(),
                        map_item.extent().yMaximum(),
                    ],
                    "layers": [layer.name(), basemap_layer.name()],
                }
            )
            progress(
                92 + int(7 * index / max(1, total)),
                _tr("导出累计形变专题图：{index}/{total}").format(
                    index=index, total=total
                ),
            )

        first_layout = project.layoutManager().layoutByName(
            _tr("累计垂直形变量_{date}").format(
                date=grid_result.periods[0].acquisition_date
            )
        )
        first_map = _item(
            first_layout,
            "m341_overview_map",
            QgsLayoutItemMap,
        )
        referenced_extent = QgsReferencedRectangle(
            first_map.extent(),
            first_map.crs(),
        )
        project.viewSettings().setPresetFullExtent(referenced_extent)
        project.viewSettings().setDefaultViewExtent(referenced_extent)

        qgz_path: Path | None = None
        project_inspection: dict[str, Any] | None = None
        if settings.export_qgz:
            qgz_path = project_dir / "ps_insar_cumulative_displacement_batch.qgz"
            if not project.write(str(qgz_path)):
                raise BatchCoreError(_tr("无法写入批量累计形变QGZ。"))
            project_inspection = _inspect_project(qgz_path, total)
            if not (
                project_inspection["read_ok"]
                and project_inspection["all_layers_valid"]
                and project_inspection["layout_count"] == total
            ):
                raise BatchCoreError(
                    _tr("QGZ质量门失败：{inspection}").format(
                        inspection=project_inspection
                    )
                )
        return {
            "qgz_path": str(qgz_path) if qgz_path else None,
            "qgz_sha256": _sha256(qgz_path) if qgz_path else None,
            "project_inspection": project_inspection,
            "exports": exports,
            "layouts": layouts,
            "input_copy_hashes": input_copy_hashes,
        }
    finally:
        project.clear()
        gc.collect()


def run_displacement_batch(
    settings: BatchMapSettings,
    plugin_dir: str | Path,
    *,
    progress: ProgressCallback | None = None,
    is_cancelled: CancelCallback | None = None,
    run_id: str | None = None,
) -> BatchBuildResult:
    """Run one non-overwriting cumulative-displacement batch job."""
    progress = progress or (lambda _value, _message: None)
    is_cancelled = is_cancelled or (lambda: False)
    plugin_dir = Path(plugin_dir).resolve()
    bundled_template = _bundled_template_path(plugin_dir)
    errors = validate_batch_settings(
        settings,
        bundled_template=bundled_template,
    )
    if errors:
        separator = "; " if language_code() == "en" else "；"
        raise BatchCoreError(separator.join(errors))

    context = RunContext.create(
        settings.output_root,
        TaskSpec(
            module_id="ps_cumulative_batch",
            module_version=BATCH_ENGINE_VERSION,
            inputs={
                "input_gpkg": settings.input_gpkg,
                "template_path": settings.template_path
                or str(bundled_template),
                "basemap_path": settings.basemap_path,
            },
            parameters={
                **asdict(settings),
                "selected_fields": list(settings.selected_fields),
                "extreme_point_layer_included": False,
            },
        ),
        run_id=run_id,
        metadata_subdir="qa",
    )
    context.mark_running()
    try:
        grid_result = build_cumulative_grid(
            settings,
            context.run_dir,
            progress=progress,
            is_cancelled=is_cancelled,
        )
        render_result = _render_project_and_maps(
            settings,
            plugin_dir,
            context,
            grid_result,
            progress=progress,
            is_cancelled=is_cancelled,
        )
        report = {
            "schema_version": "m7.2.2-batch-map-v1",
            "status": "PASS",
            "engine_version": BATCH_ENGINE_VERSION,
            "formula": "D_target - D_initial",
            "unit": "mm",
            "grid_size_m": 50.0,
            "display_bound_mm": 20.0,
            "display_bound_m": 20.0,
            "aggregation": "50 m grid median",
            "extreme_point_layer_included": False,
            "grid": {
                **asdict(grid_result),
                "output_gpkg": str(grid_result.output_gpkg),
            },
            "render": render_result,
        }
        report_path = context.run_dir / "qa" / "M7.2.2_BATCH_REPORT.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str)
            + "\n",
            encoding="utf-8",
        )
        context.mark_pass(
            {
                "status": "PASS",
                "report": str(report_path),
                "period_count": len(grid_result.periods),
                "qgz": render_result["qgz_path"],
            }
        )
        progress(100, _tr("累计形变批量专题图任务完成"))
        return BatchBuildResult(
            run_dir=context.run_dir,
            status="PASS",
            qgz_path=(
                Path(render_result["qgz_path"])
                if render_result["qgz_path"]
                else None
            ),
            grid_gpkg=grid_result.output_gpkg,
            period_count=len(grid_result.periods),
            png_count=sum(
                "png" in value for value in render_result["exports"].values()
            ),
            pdf_count=sum(
                "pdf" in value for value in render_result["exports"].values()
            ),
            report_path=report_path,
        )
    except BatchCancelled as exc:
        context.mark_cancelled(str(exc))
        raise
    except Exception as exc:
        context.mark_failed(exc)
        raise
