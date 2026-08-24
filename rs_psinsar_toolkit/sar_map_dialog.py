"""GUI for editable SAR thematic-map export."""

from __future__ import annotations

import json
from pathlib import Path

from qgis.PyQt.QtCore import QDate, QSettings, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsApplication, QgsRasterLayer

from .sar_core import inspect_raster
from .sar_map_builder import (
    SarMapBuildError,
    SarMapBuildResult,
    build_sar_map,
)
from .sar_map_settings import (
    DEFAULT_DISPLAY_METHOD,
    DEFAULT_SAR_MAP_DPI,
    DEFAULT_SAR_MAP_TITLE,
    MAX_RIGHT_PANEL_LINES,
    SarMapSettings,
    compose_right_panel,
    localized_default_display_method,
    localized_default_title,
    validate_sar_map_settings,
)


class SarMapDialog(QDialog):
    """Collect seven optional labels and export a new SAR map run."""

    def __init__(
        self,
        iface,
        parent=None,
        settings_store=None,
        initial_raster_path: str = "",
    ):
        super().__init__(parent)
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self._settings_store = (
            settings_store
            if settings_store is not None
            else QSettings("PyQGISProject", "rs_psinsar_toolkit")
        )
        self._cancel_requested = False
        self._last_result: SarMapBuildResult | None = None
        self.setObjectName("sar_map_dialog")
        self.setWindowTitle(self.tr("SAR 强度 dB 专题制图"))
        self.resize(900, 720)

        intro = QLabel(
            self.tr(
                "本模块使用已完成预处理的单波段 SAR 强度 dB GeoTIFF，生成可编辑 QGZ 工程、"
                "PNG/PDF 专题图及质量检查报告。专题图标题、右侧说明和底部制图信息均可由用户设置，"
                "较长文字支持自动换行。"
            )
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "background:#eaf3ff; border:1px solid #6a9fd4; padding:8px;"
        )
        notice = QLabel(
            self.tr(
                "输入要求：影像应已完成必要的镶嵌、裁剪和线性功率转 dB 处理。"
                "本模块不重复执行影像镶嵌、掩膜裁剪或 10 × log10(P) 转换，也不修改原始输入影像。"
                "缺少完整 Sigma0/Gamma0 定标证据时，成果仅表述为 SAR 强度 dB。"
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "background:#fff8dc; border:1px solid #d8b84c; padding:8px;"
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_input_tab(), self.tr("数据与输出"))
        self.tabs.addTab(self._build_text_tab(), self.tr("专题图设置"))
        self.tabs.addTab(self._build_export_tab(), self.tr("导出与日志"))

        self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.button_box.button(QDialogButtonBox.Close).setText(
            self.tr("关闭")
        )
        self.button_box.rejected.connect(self.close)
        root = QVBoxLayout(self)
        root.addWidget(intro)
        root.addWidget(notice)
        root.addWidget(self.tabs, 1)
        root.addWidget(self.button_box)

        self._connect_signals()
        self._load_preferences()
        if initial_raster_path:
            self.raster_edit.setText(initial_raster_path)
            self.fill_raster_metadata()
        self._sync_optional_controls()
        self._append_log(
            self.tr(
                "SAR 强度 dB 专题制图模块已就绪。请确认输入影像、专题图设置和导出选项。"
            )
        )

    def _build_input_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        input_group = QGroupBox(self.tr("SAR 强度 dB 影像"))
        input_form = QFormLayout(input_group)
        raster_row = QHBoxLayout()
        self.raster_edit = QLineEdit()
        self.raster_edit.setObjectName("sar_map_raster_edit")
        self.raster_edit.setPlaceholderText(
            self.tr("选择单波段 SAR 强度 dB GeoTIFF")
        )
        self.raster_button = QPushButton(self.tr("浏览…"))
        self.raster_button.setObjectName("sar_map_raster_button")
        self.inspect_button = QPushButton(self.tr("读取影像信息"))
        self.inspect_button.setObjectName("sar_map_inspect_button")
        raster_row.addWidget(self.raster_edit, 1)
        raster_row.addWidget(self.raster_button)
        raster_row.addWidget(self.inspect_button)
        input_form.addRow(self.tr("输入影像："), raster_row)

        output_group = QGroupBox(self.tr("输出位置"))
        output_layout = QHBoxLayout(output_group)
        self.output_edit = QLineEdit()
        self.output_edit.setObjectName("sar_map_output_edit")
        self.output_edit.setPlaceholderText(
            self.tr("选择输出根目录；任务将自动创建时间戳子目录")
        )
        self.output_button = QPushButton(self.tr("浏览…"))
        self.output_button.setObjectName("sar_map_output_button")
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(self.output_button)

        boundary = QLabel(
            self.tr(
                "每次任务均在输出根目录中创建独立的时间戳子目录，并复制一份输入 SAR 强度 dB 影像，"
                "以便 QGZ 工程移动和后续人工调整；原始影像及已有成果不会被覆盖。"
            )
        )
        boundary.setWordWrap(True)
        boundary.setStyleSheet("color:#555555;")

        layout.addWidget(input_group)
        layout.addWidget(output_group)
        layout.addWidget(boundary)
        layout.addStretch(1)
        return tab

    @staticmethod
    def _optional_text_row(
        checkbox: QCheckBox,
        edit: QLineEdit,
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(checkbox)
        row.addWidget(edit, 1)
        return row

    def _build_text_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        title_group = QGroupBox(self.tr("标题"))
        title_form = QFormLayout(title_group)
        self.title_edit = QLineEdit(localized_default_title())
        self.title_edit.setObjectName("sar_map_title_edit")
        title_form.addRow(self.tr("专题图标题："), self.title_edit)

        right_group = QGroupBox(self.tr("右侧说明信息"))
        right_form = QFormLayout(right_group)
        self.show_crs = QCheckBox(self.tr("显示"))
        self.show_crs.setObjectName("sar_map_show_crs")
        self.show_crs.setChecked(True)
        self.crs_edit = QLineEdit()
        self.crs_edit.setObjectName("sar_map_crs_edit")
        self.crs_edit.setMaxLength(120)
        self.crs_edit.setPlaceholderText(
            self.tr("例如：WGS 84 / UTM zone 50N（EPSG:32650）")
        )
        right_form.addRow(
            self.tr("坐标参考系："),
            self._optional_text_row(self.show_crs, self.crs_edit),
        )

        self.show_resolution = QCheckBox(self.tr("显示"))
        self.show_resolution.setObjectName("sar_map_show_resolution")
        self.show_resolution.setChecked(True)
        self.resolution_edit = QLineEdit()
        self.resolution_edit.setObjectName("sar_map_resolution_edit")
        self.resolution_edit.setMaxLength(60)
        self.resolution_edit.setPlaceholderText(self.tr("例如：3 m"))
        right_form.addRow(
            self.tr("空间分辨率："),
            self._optional_text_row(
                self.show_resolution,
                self.resolution_edit,
            ),
        )

        self.show_display_method = QCheckBox(self.tr("显示"))
        self.show_display_method.setObjectName(
            "sar_map_show_display_method"
        )
        self.show_display_method.setChecked(True)
        self.display_method_edit = QLineEdit(
            localized_default_display_method()
        )
        self.display_method_edit.setObjectName("sar_map_display_method_edit")
        self.display_method_edit.setMaxLength(120)
        self.display_method_edit.setPlaceholderText(
            self.tr("例如：2%—98%线性拉伸")
        )
        right_form.addRow(
            self.tr("显示方法："),
            self._optional_text_row(
                self.show_display_method,
                self.display_method_edit,
            ),
        )

        footer_group = QGroupBox(self.tr("底部制图信息"))
        footer_form = QFormLayout(footer_group)
        self.show_data_source = QCheckBox(self.tr("显示"))
        self.show_data_source.setObjectName("sar_map_show_data_source")
        self.show_data_source.setChecked(True)
        self.data_source_edit = QLineEdit()
        self.data_source_edit.setObjectName("sar_map_data_source_edit")
        self.data_source_edit.setMaxLength(160)
        self.data_source_edit.setPlaceholderText(
            self.tr("例如：BC2 SM ORG VV")
        )
        footer_form.addRow(
            self.tr("数据来源："),
            self._optional_text_row(
                self.show_data_source,
                self.data_source_edit,
            ),
        )

        self.show_acquisition_time = QCheckBox(self.tr("显示"))
        self.show_acquisition_time.setObjectName(
            "sar_map_show_acquisition_time"
        )
        self.show_acquisition_time.setChecked(True)
        self.acquisition_time_edit = QLineEdit()
        self.acquisition_time_edit.setObjectName(
            "sar_map_acquisition_time_edit"
        )
        self.acquisition_time_edit.setMaxLength(160)
        self.acquisition_time_edit.setPlaceholderText(
            self.tr("可填写单日、日期范围或多期说明")
        )
        footer_form.addRow(
            self.tr("数据拍摄时间："),
            self._optional_text_row(
                self.show_acquisition_time,
                self.acquisition_time_edit,
            ),
        )

        date_row = QHBoxLayout()
        self.show_production_date = QCheckBox(self.tr("显示"))
        self.show_production_date.setObjectName(
            "sar_map_show_production_date"
        )
        self.show_production_date.setChecked(True)
        self.use_current_date = QCheckBox(self.tr("使用当前日期"))
        self.use_current_date.setObjectName("sar_map_use_current_date")
        self.use_current_date.setChecked(True)
        self.production_date_edit = QDateEdit(QDate.currentDate())
        self.production_date_edit.setObjectName(
            "sar_map_production_date_edit"
        )
        self.production_date_edit.setCalendarPopup(True)
        self.production_date_edit.setDisplayFormat("yyyy-MM-dd")
        date_row.addWidget(self.show_production_date)
        date_row.addWidget(self.use_current_date)
        date_row.addWidget(self.production_date_edit)
        date_row.addStretch(1)
        footer_form.addRow(self.tr("制图时间："), date_row)

        self.show_production_unit = QCheckBox(self.tr("显示"))
        self.show_production_unit.setObjectName(
            "sar_map_show_production_unit"
        )
        self.show_production_unit.setChecked(False)
        self.production_unit_edit = QLineEdit()
        self.production_unit_edit.setObjectName(
            "sar_map_production_unit_edit"
        )
        self.production_unit_edit.setMaxLength(120)
        self.production_unit_edit.setPlaceholderText(
            self.tr("请输入制作单位")
        )
        footer_form.addRow(
            self.tr("制作单位："),
            self._optional_text_row(
                self.show_production_unit,
                self.production_unit_edit,
            ),
        )

        wrap_note = QLabel(
            self.tr(
                "较长内容将根据模板宽度自动换行；取消显示后，其余内容自动上移，不保留空行。"
            )
        )
        wrap_note.setWordWrap(True)
        wrap_note.setStyleSheet("color:#555555;")

        preview_group = QGroupBox(self.tr("右侧说明预览"))
        preview_layout = QVBoxLayout(preview_group)
        self.right_preview_status = QLabel()
        self.right_preview_status.setObjectName(
            "sar_map_right_preview_status"
        )
        self.right_preview = QPlainTextEdit()
        self.right_preview.setObjectName("sar_map_right_preview")
        self.right_preview.setReadOnly(True)
        self.right_preview.setMaximumHeight(150)
        self.right_preview.setStyleSheet(
            "background:#f7f7f7;"
            "font-size:11pt;"
        )
        preview_layout.addWidget(self.right_preview_status)
        preview_layout.addWidget(self.right_preview)

        layout.addWidget(title_group)
        layout.addWidget(right_group)
        layout.addWidget(preview_group)
        layout.addWidget(footer_group)
        layout.addWidget(wrap_note)
        layout.addStretch(1)
        return tab

    def _build_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        export_group = QGroupBox(self.tr("输出"))
        export_form = QFormLayout(export_group)
        output_row = QHBoxLayout()
        self.export_qgz = QCheckBox(self.tr("可编辑 QGZ"))
        self.export_qgz.setObjectName("sar_map_export_qgz")
        self.export_qgz.setChecked(True)
        self.export_png = QCheckBox("PNG")
        self.export_png.setObjectName("sar_map_export_png")
        self.export_png.setChecked(True)
        self.export_pdf = QCheckBox("PDF")
        self.export_pdf.setObjectName("sar_map_export_pdf")
        self.export_pdf.setChecked(True)
        output_row.addWidget(self.export_qgz)
        output_row.addWidget(self.export_png)
        output_row.addWidget(self.export_pdf)
        output_row.addStretch(1)
        export_form.addRow(self.tr("输出类型："), output_row)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setObjectName("sar_map_dpi_spin")
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(DEFAULT_SAR_MAP_DPI)
        self.dpi_spin.setSuffix(" dpi")
        export_form.addRow(
            self.tr("导出分辨率（DPI）："), self.dpi_spin
        )

        self.status_label = QLabel(self.tr("请检查当前设置"))
        self.status_label.setObjectName("sar_map_status_label")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("sar_map_progress_bar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setObjectName("sar_map_log_edit")
        self.log_edit.setReadOnly(True)

        actions = QHBoxLayout()
        self.validate_button = QPushButton(self.tr("检查当前设置"))
        self.validate_button.setObjectName("sar_map_validate_button")
        self.run_button = QPushButton(self.tr("生成专题图"))
        self.run_button.setObjectName("sar_map_run_button")
        self.run_button.setEnabled(False)
        self.cancel_button = QPushButton(self.tr("取消任务"))
        self.cancel_button.setObjectName("sar_map_cancel_button")
        self.cancel_button.setEnabled(False)
        self.open_button = QPushButton(self.tr("打开输出目录"))
        self.open_button.setObjectName("sar_map_open_button")
        self.open_button.setEnabled(False)
        self.clear_button = QPushButton(self.tr("清空日志"))
        self.clear_button.setObjectName("sar_map_clear_button")
        actions.addWidget(self.validate_button)
        actions.addWidget(self.run_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.open_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)

        layout.addWidget(export_group)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_edit, 1)
        layout.addLayout(actions)
        return tab

    def _connect_signals(self) -> None:
        self.raster_button.clicked.connect(self._browse_raster)
        self.output_button.clicked.connect(self._browse_output)
        self.inspect_button.clicked.connect(self.fill_raster_metadata)
        self.validate_button.clicked.connect(self.validate_current_settings)
        self.run_button.clicked.connect(self.run_generation)
        self.cancel_button.clicked.connect(self.request_cancel)
        self.open_button.clicked.connect(self.open_last_output)
        self.clear_button.clicked.connect(self.log_edit.clear)
        for checkbox in (
            self.show_crs,
            self.show_resolution,
            self.show_display_method,
            self.show_data_source,
            self.show_acquisition_time,
            self.show_production_date,
            self.use_current_date,
            self.show_production_unit,
        ):
            checkbox.toggled.connect(self._sync_optional_controls)
        invalidators = (
            self.raster_edit,
            self.output_edit,
            self.title_edit,
            self.crs_edit,
            self.resolution_edit,
            self.display_method_edit,
            self.data_source_edit,
            self.acquisition_time_edit,
            self.production_unit_edit,
        )
        for edit in invalidators:
            edit.textChanged.connect(self._invalidate_validation)
        for edit in (
            self.crs_edit,
            self.resolution_edit,
            self.display_method_edit,
        ):
            edit.textChanged.connect(self._update_right_preview)
        self.production_date_edit.dateChanged.connect(
            self._invalidate_validation
        )
        for checkbox in (
            self.show_crs,
            self.show_resolution,
            self.show_display_method,
            self.show_data_source,
            self.show_acquisition_time,
            self.show_production_date,
            self.use_current_date,
            self.show_production_unit,
            self.export_qgz,
            self.export_png,
            self.export_pdf,
        ):
            checkbox.toggled.connect(self._invalidate_validation)

    def _sync_optional_controls(self) -> None:
        self.crs_edit.setEnabled(self.show_crs.isChecked())
        self.resolution_edit.setEnabled(self.show_resolution.isChecked())
        self.display_method_edit.setEnabled(
            self.show_display_method.isChecked()
        )
        self.data_source_edit.setEnabled(
            self.show_data_source.isChecked()
        )
        self.acquisition_time_edit.setEnabled(
            self.show_acquisition_time.isChecked()
        )
        date_visible = self.show_production_date.isChecked()
        self.use_current_date.setEnabled(date_visible)
        self.production_date_edit.setEnabled(
            date_visible and not self.use_current_date.isChecked()
        )
        if date_visible and self.use_current_date.isChecked():
            self.production_date_edit.setDate(QDate.currentDate())
        self.production_unit_edit.setEnabled(
            self.show_production_unit.isChecked()
        )
        self._update_right_preview()

    def _update_right_preview(self) -> None:
        """Show the exact wrapped right-panel text before map export."""
        if not hasattr(self, "right_preview"):
            return
        text = compose_right_panel(self.current_settings())
        line_count = len(text.splitlines()) if text else 0
        self.right_preview.setPlainText(
            text if text else self.tr("（右侧三项全部隐藏）")
        )
        self.right_preview_status.setText(
            self.tr(
                "当前占用 {line_count}/{maximum} 行；超过 {maximum} 行时需要精简右侧说明内容。"
            ).format(
                line_count=line_count,
                maximum=MAX_RIGHT_PANEL_LINES,
            )
        )
        if line_count > MAX_RIGHT_PANEL_LINES:
            self.right_preview_status.setStyleSheet(
                "color:#b00020; font-weight:bold;"
            )
            self.right_preview.setStyleSheet(
                "background:#fff0f0; border:1px solid #b00020;"
                "font-size:11pt;"
            )
        else:
            self.right_preview_status.setStyleSheet("color:#555555;")
            self.right_preview.setStyleSheet(
                "background:#f7f7f7;"
                "font-size:11pt;"
            )

    def _invalidate_validation(self) -> None:
        self.run_button.setEnabled(False)
        if not self._cancel_requested:
            self.status_label.setText(
                self.tr("设置已变化，请重新检查")
            )

    def _browse_raster(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择单波段 SAR 强度 dB GeoTIFF"),
            self.raster_edit.text(),
            "GeoTIFF (*.tif *.tiff)",
        )
        if path:
            self.raster_edit.setText(path)
            self.fill_raster_metadata()

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择输出根目录"),
            self.output_edit.text(),
        )
        if path:
            self.output_edit.setText(path)

    @staticmethod
    def _format_resolution(value: float) -> str:
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:.6f}".rstrip("0").rstrip(".")

    def fill_raster_metadata(self) -> None:
        path = Path(self.raster_edit.text().strip())
        if not path.is_file():
            self._append_log(
                self.tr("[检查] 请先选择存在的 GeoTIFF。")
            )
            return
        try:
            info = inspect_raster(path)
            layer = QgsRasterLayer(str(path), "metadata_probe", "gdal")
            if not layer.isValid():
                raise ValueError(self.tr("QGIS 无法读取该栅格。"))
            description = layer.crs().description().strip()
            authid = layer.crs().authid().strip()
            if description and authid:
                crs_text = f"{description}（{authid}）"
            else:
                crs_text = authid or description
            self.crs_edit.setText(crs_text)
            x_res = float(info["x_resolution"])
            y_res = float(info["y_resolution"])
            if abs(x_res - y_res) < 1e-9:
                resolution = f"{self._format_resolution(x_res)} m"
            else:
                resolution = (
                    f"{self._format_resolution(x_res)} × "
                    f"{self._format_resolution(y_res)} m"
                )
            self.resolution_edit.setText(resolution)
            self._append_log(
                self.tr(
                    "[读取] {crs}；分辨率 {resolution}；{width}×{height}；{bands} 波段。"
                ).format(
                    crs=authid or self.tr("CRS 未知"),
                    resolution=resolution,
                    width=info["width"],
                    height=info["height"],
                    bands=info["band_count"],
                )
            )
        except Exception as exc:
            self._append_log(
                self.tr("[读取失败] {error}").format(error=exc)
            )

    def current_settings(self) -> SarMapSettings:
        return SarMapSettings(
            raster_path=self.raster_edit.text().strip(),
            output_root=self.output_edit.text().strip(),
            title=self.title_edit.text().strip(),
            show_crs=self.show_crs.isChecked(),
            crs_text=self.crs_edit.text().strip(),
            show_resolution=self.show_resolution.isChecked(),
            resolution_text=self.resolution_edit.text().strip(),
            show_display_method=self.show_display_method.isChecked(),
            display_method_text=self.display_method_edit.text().strip(),
            show_data_source=self.show_data_source.isChecked(),
            data_source=self.data_source_edit.text().strip(),
            show_acquisition_time=(
                self.show_acquisition_time.isChecked()
            ),
            acquisition_time=self.acquisition_time_edit.text().strip(),
            show_production_date=(
                self.show_production_date.isChecked()
            ),
            production_date=self.production_date_edit.date().toString(
                "yyyy-MM-dd"
            ),
            use_current_date=self.use_current_date.isChecked(),
            show_production_unit=(
                self.show_production_unit.isChecked()
            ),
            production_unit=self.production_unit_edit.text().strip(),
            export_qgz=self.export_qgz.isChecked(),
            export_png=self.export_png.isChecked(),
            export_pdf=self.export_pdf.isChecked(),
            dpi=self.dpi_spin.value(),
        )

    def validate_current_settings(self) -> list[str]:
        settings = self.current_settings()
        errors = validate_sar_map_settings(settings)
        self._append_log(self.tr("设置快照："))
        self._append_log(
            json.dumps(settings.__dict__, ensure_ascii=False, indent=2)
        )
        if errors:
            self.status_label.setText(
                self.tr("设置检查未通过：{count} 项").format(
                    count=len(errors)
                )
            )
            self.run_button.setEnabled(False)
            for error in errors:
                self._append_log(
                    self.tr("[需要处理] {error}").format(error=error)
                )
        else:
            self.status_label.setText(
                self.tr("设置检查通过，可以生成专题图")
            )
            self.run_button.setEnabled(True)
            self._append_log(
                self.tr("[PASS] 当前设置通过只读检查。")
            )
            self._save_preferences()
        return errors

    def run_generation(self) -> None:
        if self.validate_current_settings():
            return
        self._cancel_requested = False
        self._last_result = None
        self._set_busy(True)
        self.progress_bar.setValue(0)
        self._append_log(self.tr("开始生成 SAR 强度 dB 专题图。"))
        try:
            result = build_sar_map(
                self.current_settings(),
                self.plugin_dir,
                progress=self._on_progress,
                is_cancelled=lambda: self._cancel_requested,
            )
            self._last_result = result
            self.open_button.setEnabled(True)
            self.status_label.setText(
                self.tr("SAR 强度 dB 专题图完成：{status}").format(
                    status=result.status
                )
            )
            self._append_log(
                self.tr("[{status}] 输出目录：{directory}").format(
                    status=result.status,
                    directory=result.run_dir,
                )
            )
        except (SarMapBuildError, OSError, RuntimeError, ValueError) as exc:
            self.status_label.setText(
                self.tr("生成失败，请查看日志和失败记录")
            )
            self._append_log(f"[FAILED] {exc}")
        finally:
            self._set_busy(False)

    def request_cancel(self) -> None:
        self._cancel_requested = True
        self.cancel_button.setEnabled(False)
        self.status_label.setText(
            self.tr("已请求取消；将在当前步骤结束后停止")
        )
        self._append_log(self.tr("[取消] 已收到取消请求。"))

    def open_last_output(self) -> None:
        if self._last_result is not None:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._last_result.run_dir))
            )

    def _on_progress(self, value: int, message: str) -> None:
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        self._append_log(f"[{value}%] {message}")
        QgsApplication.processEvents()

    def _set_busy(self, busy: bool) -> None:
        self.tabs.setEnabled(not busy)
        self.validate_button.setEnabled(not busy)
        self.run_button.setEnabled(False if busy else self.run_button.isEnabled())
        self.cancel_button.setEnabled(busy)
        self.clear_button.setEnabled(not busy)
        self.button_box.setEnabled(not busy)
        if not busy:
            self.cancel_button.setEnabled(False)

    def _load_preferences(self) -> None:
        store = self._settings_store
        self.raster_edit.setText(
            store.value("sar_map/raster_path", "", type=str)
        )
        self.output_edit.setText(
            store.value("sar_map/output_root", "", type=str)
        )
        self.title_edit.setText(
            store.value(
                "sar_map/title",
                localized_default_title(),
                type=str,
            )
        )
        boolean_widgets = (
            ("show_crs", self.show_crs, True),
            ("show_resolution", self.show_resolution, True),
            ("show_display_method", self.show_display_method, True),
            ("show_data_source", self.show_data_source, True),
            ("show_acquisition_time", self.show_acquisition_time, True),
            ("show_production_date", self.show_production_date, True),
            ("use_current_date", self.use_current_date, True),
            ("show_production_unit", self.show_production_unit, False),
            ("export_qgz", self.export_qgz, True),
            ("export_png", self.export_png, True),
            ("export_pdf", self.export_pdf, True),
        )
        for key, widget, default in boolean_widgets:
            widget.setChecked(
                store.value(f"sar_map/{key}", default, type=bool)
            )
        text_widgets = (
            ("crs_text", self.crs_edit, ""),
            ("resolution_text", self.resolution_edit, ""),
            (
                "display_method_text",
                self.display_method_edit,
                localized_default_display_method(),
            ),
            ("data_source", self.data_source_edit, ""),
            ("acquisition_time", self.acquisition_time_edit, ""),
            ("production_unit", self.production_unit_edit, ""),
        )
        for key, widget, default in text_widgets:
            widget.setText(
                store.value(f"sar_map/{key}", default, type=str)
            )
        stored_date = store.value(
            "sar_map/production_date",
            QDate.currentDate().toString("yyyy-MM-dd"),
            type=str,
        )
        parsed_date = QDate.fromString(stored_date, "yyyy-MM-dd")
        self.production_date_edit.setDate(
            parsed_date if parsed_date.isValid() else QDate.currentDate()
        )
        self.dpi_spin.setValue(
            store.value(
                "sar_map/dpi",
                DEFAULT_SAR_MAP_DPI,
                type=int,
            )
        )

    def _save_preferences(self) -> None:
        settings = self.current_settings()
        store = self._settings_store
        for key, value in settings.__dict__.items():
            store.setValue(f"sar_map/{key}", value)
        store.sync()

    def _append_log(self, text: str) -> None:
        self.log_edit.appendPlainText(text)
