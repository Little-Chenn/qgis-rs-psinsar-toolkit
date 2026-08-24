"""GUI for M7.2.2 cumulative-displacement batch thematic maps."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from qgis.PyQt.QtCore import QDate, QSettings, QUrl, Qt
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsApplication

from .displacement_batch_builder import run_displacement_batch
from .displacement_batch_core import (
    BatchCancelled,
    BatchCoreError,
)
from .displacement_batch_settings import (
    DEFAULT_DPI,
    BatchMapSettings,
    TimeField,
    localized_default_data_source,
    localized_default_title_pattern,
    read_time_catalog,
    validate_batch_settings,
)


class DisplacementBatchDialog(QDialog):
    """Collect one safe non-overwriting cumulative-displacement batch job."""

    def __init__(self, iface, parent=None, settings_store=None):
        super().__init__(parent)
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self._settings = (
            settings_store
            if settings_store is not None
            else QSettings("PyQGISProject", "rs_psinsar_toolkit")
        )
        self._catalog: list[TimeField] = []
        self._cancel_requested = False
        self._running = False
        self._last_run_dir: Path | None = None
        self.setObjectName("displacement_batch_dialog")
        self.setWindowTitle(self.tr("PS-InSAR 累计形变批量制图"))
        self.resize(930, 760)

        intro = QLabel(
            self.tr(
                "本模块从多时相 GeoPackage 读取各期 PS 点形变量，以初始时相为基准逐点计算累计形变量 "
                "ΔDₜ = Dₜ − D₀，并按 50 m 网格统计中位数，批量生成可编辑 QGZ、PNG/PDF 专题图及"
                "质量检查报告。每次任务创建独立输出目录，不修改输入数据。"
            )
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "background:#eaf3ff; border:1px solid #6a9fd4; padding:8px;"
        )
        warning = QLabel(
            self.tr(
                "输入数据应包含且仅包含一个初始时相，所有形变量字段单位应为 mm。正值表示垂直向上，"
                "负值表示垂直向下。本模块不自动判定极端值、异常点或物理原因。"
            )
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background:#fff4ce; border:1px solid #e0b400; padding:8px;"
        )

        tabs = QTabWidget()
        tabs.addTab(self._build_data_tab(), self.tr("数据与时相"))
        tabs.addTab(self._build_layout_tab(), self.tr("模板与制图信息"))
        tabs.addTab(self._build_execution_tab(), self.tr("输出与日志"))
        close_button = QPushButton(self.tr("关闭"))
        close_button.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close_button)
        root = QVBoxLayout(self)
        root.addWidget(intro)
        root.addWidget(warning)
        root.addWidget(tabs)
        root.addLayout(footer)
        self._connect()
        self._load_preferences()
        self._sync_controls()
        self._append_log(
            self.tr(
                "PS-InSAR 累计形变批量制图模块已就绪。请扫描时相目录、选择输出时相，"
                "并确认底图、模板、制图信息和导出选项。"
            )
        )

    def _path_row(
        self,
        placeholder: str,
        button_text: str | None = None,
    ):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        button = QPushButton(button_text or self.tr("浏览…"))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return container, edit, button

    def _build_data_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        input_group = QGroupBox(self.tr("PS-InSAR 多时相 GeoPackage"))
        input_form = QFormLayout(input_group)
        row, self.gpkg_edit, self.gpkg_button = self._path_row(
            self.tr("选择包含 ps_timeseries_points 和 time_catalog 的多时相 GeoPackage")
        )
        input_form.addRow(self.tr("输入数据："), row)
        self.scan_button = QPushButton(self.tr("扫描时相（只读）"))
        self.scan_button.setObjectName("scan_time_catalog_button")
        self.catalog_label = QLabel(self.tr("尚未扫描"))
        catalog_row = QHBoxLayout()
        catalog_row.addWidget(self.scan_button)
        catalog_row.addWidget(self.catalog_label, 1)
        input_form.addRow(self.tr("时相目录："), catalog_row)

        period_group = QGroupBox(self.tr("输出时相"))
        period_layout = QVBoxLayout(period_group)
        note = QLabel(
            self.tr(
                "D₀ 表示初始时相形变量，Dₜ 表示目标时相形变量。默认输出累计形变量 "
                "ΔDₜ = Dₜ − D₀；初始时相结果恒为 0 mm，因此默认不输出。"
            )
        )
        note.setWordWrap(True)
        self.period_list = QListWidget()
        self.period_list.setObjectName("period_list")
        self.period_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        buttons = QHBoxLayout()
        self.select_all_button = QPushButton(self.tr("选择全部后续时相"))
        self.clear_periods_button = QPushButton(self.tr("清空选择"))
        self.include_initial_checkbox = QCheckBox(
            self.tr("同时输出初始时相图（D₀ − D₀ = 0 mm）")
        )
        self.include_initial_checkbox.setChecked(False)
        buttons.addWidget(self.select_all_button)
        buttons.addWidget(self.clear_periods_button)
        buttons.addWidget(self.include_initial_checkbox)
        buttons.addStretch(1)
        period_layout.addWidget(note)
        period_layout.addWidget(self.period_list, 1)
        period_layout.addLayout(buttons)

        base_group = QGroupBox(self.tr("底图与输出"))
        base_form = QFormLayout(base_group)
        row, self.basemap_edit, self.basemap_button = self._path_row(
            self.tr("选择本地卫星影像底图")
        )
        base_form.addRow(self.tr("卫星底图："), row)
        row, self.output_edit, self.output_button = self._path_row(
            self.tr("选择输出根目录；任务将自动创建时间戳子目录")
        )
        base_form.addRow(self.tr("输出根目录："), row)

        layout.addWidget(input_group)
        layout.addWidget(period_group, 1)
        layout.addWidget(base_group)
        return tab

    def _build_layout_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        template_group = QGroupBox(self.tr("专题图模板"))
        template_form = QFormLayout(template_group)
        row, self.template_edit, self.template_button = self._path_row(
            self.tr("留空时使用插件内置模板；也可选择已确认的 QPT 模板")
        )
        template_form.addRow(self.tr("QPT模板："), row)
        template_note = QLabel(
            self.tr("内置模板来源于已确认模板；外部 QPT 仅以只读方式加载，不修改原文件。")
        )
        template_note.setWordWrap(True)
        template_form.addRow("", template_note)

        title_group = QGroupBox(self.tr("标题"))
        title_form = QFormLayout(title_group)
        self.title_pattern_edit = QLineEdit(localized_default_title_pattern())
        self.title_pattern_edit.setObjectName("batch_title_pattern")
        title_form.addRow(self.tr("标题格式："), self.title_pattern_edit)
        title_note = QLabel(
            self.tr("请保留 {initial_date}（初始日期）和 {target_date}（目标日期）两个占位符。")
        )
        title_form.addRow("", title_note)

        metadata_group = QGroupBox(self.tr("制图信息"))
        metadata_form = QFormLayout(metadata_group)
        self.show_source = QCheckBox(self.tr("显示"))
        self.show_source.setChecked(True)
        self.source_edit = QLineEdit(localized_default_data_source())
        row_layout = QHBoxLayout()
        row_layout.addWidget(self.show_source)
        row_layout.addWidget(self.source_edit, 1)
        metadata_form.addRow(self.tr("数据来源："), row_layout)

        self.show_period = QCheckBox(self.tr("显示（自动填写）"))
        self.show_period.setChecked(True)
        metadata_form.addRow(self.tr("数据拍摄时间："), self.show_period)

        self.show_date = QCheckBox(self.tr("显示"))
        self.show_date.setChecked(True)
        self.production_date = QDateEdit(QDate.currentDate())
        self.production_date.setCalendarPopup(True)
        self.production_date.setDisplayFormat("yyyy-MM-dd")
        row_layout = QHBoxLayout()
        row_layout.addWidget(self.show_date)
        row_layout.addWidget(self.production_date)
        row_layout.addStretch(1)
        metadata_form.addRow(self.tr("制图时间："), row_layout)

        self.show_unit = QCheckBox(self.tr("显示"))
        self.show_unit.setChecked(False)
        self.unit_edit = QLineEdit()
        self.unit_edit.setPlaceholderText(self.tr("请输入制作单位"))
        row_layout = QHBoxLayout()
        row_layout.addWidget(self.show_unit)
        row_layout.addWidget(self.unit_edit, 1)
        metadata_form.addRow(self.tr("制作单位："), row_layout)

        scientific_note = QLabel(
            self.tr(
                "计算方法与结果说明：先对每个 PS 点计算目标时相与初始时相之差 "
                "ΔDₜ = Dₜ − D₀，再统计每个 50 m 网格内有效点差值的中位数。结果单位为 mm；"
                "正值表示垂直向上，负值表示垂直向下。专题图统一采用 −20 mm 和 20 mm 作为"
                "外侧分级界限，不叠加原始极端点。"
            )
        )
        scientific_note.setWordWrap(True)
        scientific_note.setStyleSheet("color: #555555;")
        layout.addWidget(template_group)
        layout.addWidget(title_group)
        layout.addWidget(metadata_group)
        layout.addWidget(scientific_note)
        layout.addStretch(1)
        return tab

    def _build_execution_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        output_group = QGroupBox(self.tr("输出格式"))
        output_form = QFormLayout(output_group)
        formats = QHBoxLayout()
        self.export_qgz = QCheckBox(self.tr("可编辑 QGZ"))
        self.export_png = QCheckBox("PNG")
        self.export_pdf = QCheckBox("PDF")
        for checkbox in (self.export_qgz, self.export_png, self.export_pdf):
            checkbox.setChecked(True)
            formats.addWidget(checkbox)
        formats.addStretch(1)
        output_form.addRow(self.tr("输出："), formats)
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(DEFAULT_DPI)
        self.dpi_spin.setSuffix(" dpi")
        output_form.addRow(self.tr("导出分辨率（DPI）："), self.dpi_spin)

        self.status_label = QLabel(self.tr("请扫描时相目录并检查设置"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        actions = QHBoxLayout()
        self.validate_button = QPushButton(self.tr("检查当前设置"))
        self.run_button = QPushButton(self.tr("开始批量制图"))
        self.cancel_button = QPushButton(self.tr("取消任务"))
        self.open_button = QPushButton(self.tr("打开输出目录"))
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.open_button.setEnabled(False)
        for button in (
            self.validate_button,
            self.run_button,
            self.cancel_button,
            self.open_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addWidget(output_group)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.log, 1)
        layout.addLayout(actions)
        return tab

    def _connect(self) -> None:
        self.gpkg_button.clicked.connect(self._browse_gpkg)
        self.scan_button.clicked.connect(self.scan_catalog)
        self.basemap_button.clicked.connect(self._browse_basemap)
        self.output_button.clicked.connect(self._browse_output)
        self.template_button.clicked.connect(self._browse_template)
        self.select_all_button.clicked.connect(self.select_all_periods)
        self.clear_periods_button.clicked.connect(
            self.period_list.clearSelection
        )
        self.show_source.toggled.connect(self._sync_controls)
        self.show_date.toggled.connect(self._sync_controls)
        self.show_unit.toggled.connect(self._sync_controls)
        self.validate_button.clicked.connect(self.validate_current)
        self.run_button.clicked.connect(self.run_batch)
        self.cancel_button.clicked.connect(self.request_cancel)
        self.open_button.clicked.connect(self.open_output)

    def _load_preferences(self) -> None:
        prefix = "m722/"
        self.gpkg_edit.setText(
            str(self._settings.value(prefix + "input_gpkg", ""))
        )
        self.basemap_edit.setText(
            str(self._settings.value(prefix + "basemap", ""))
        )
        self.output_edit.setText(
            str(self._settings.value(prefix + "output_root", ""))
        )
        self.template_edit.setText(
            str(self._settings.value(prefix + "template", ""))
        )
        if self.gpkg_edit.text().strip():
            self.scan_catalog()

    def _save_preferences(self) -> None:
        prefix = "m722/"
        self._settings.setValue(prefix + "input_gpkg", self.gpkg_edit.text())
        self._settings.setValue(prefix + "basemap", self.basemap_edit.text())
        self._settings.setValue(prefix + "output_root", self.output_edit.text())
        self._settings.setValue(prefix + "template", self.template_edit.text())
        self._settings.sync()

    def _sync_controls(self) -> None:
        self.source_edit.setEnabled(self.show_source.isChecked())
        self.production_date.setEnabled(self.show_date.isChecked())
        self.unit_edit.setEnabled(self.show_unit.isChecked())

    def scan_catalog(self) -> None:
        path = self.gpkg_edit.text().strip()
        self.period_list.clear()
        self._catalog = []
        if not path:
            self.catalog_label.setText(self.tr("请选择多时相 GeoPackage"))
            return
        try:
            self._catalog = read_time_catalog(path)
            initial = [item for item in self._catalog if item.is_initial]
            targets = [item for item in self._catalog if not item.is_initial]
            if len(initial) != 1:
                raise ValueError(self.tr("初始时相数量不是1。"))
            for period in targets:
                item = QListWidgetItem(period.acquisition_date)
                item.setToolTip(
                    self.tr("内部字段：{field}").format(
                        field=period.field_name
                    )
                )
                item.setData(Qt.ItemDataRole.UserRole, period.field_name)
                self.period_list.addItem(item)
                item.setSelected(True)
            self.catalog_label.setText(
                self.tr(
                    "初始时相：{initial_date}；后续时相：{count} 期；"
                    "形变量单位：{unit}"
                ).format(
                    initial_date=initial[0].acquisition_date,
                    count=len(targets),
                    unit=initial[0].unit,
                )
            )
            self._append_log(
                self.tr(
                    "[PASS] 时相目录：初始1期，后续{count}期。"
                ).format(count=len(targets))
            )
        except Exception as exc:
            self.catalog_label.setText(self.tr("扫描失败"))
            self._append_log(
                self.tr("[FAILED] 时相扫描：{error}").format(error=exc)
            )

    def select_all_periods(self) -> None:
        self.period_list.selectAll()

    def _selected_fields(self) -> tuple[str, ...]:
        selected = [
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.period_list.selectedItems()
        ]
        order = {
            item.field_name: item.ordinal for item in self._catalog
        }
        selected.sort(key=lambda value: order.get(value, 10**9))
        if self.include_initial_checkbox.isChecked():
            initial = [item for item in self._catalog if item.is_initial]
            if initial:
                selected.insert(0, initial[0].field_name)
        return tuple(selected)

    def current_settings(self) -> BatchMapSettings:
        return BatchMapSettings(
            input_gpkg=self.gpkg_edit.text().strip(),
            template_path=self.template_edit.text().strip(),
            basemap_path=self.basemap_edit.text().strip(),
            output_root=self.output_edit.text().strip(),
            selected_fields=self._selected_fields(),
            include_initial_map=self.include_initial_checkbox.isChecked(),
            title_pattern=self.title_pattern_edit.text().strip(),
            show_data_source=self.show_source.isChecked(),
            data_source=self.source_edit.text().strip(),
            show_monitoring_period=self.show_period.isChecked(),
            show_production_date=self.show_date.isChecked(),
            production_date=self.production_date.date().toString("yyyy-MM-dd"),
            show_production_unit=self.show_unit.isChecked(),
            production_unit=self.unit_edit.text().strip(),
            export_qgz=self.export_qgz.isChecked(),
            export_png=self.export_png.isChecked(),
            export_pdf=self.export_pdf.isChecked(),
            dpi=self.dpi_spin.value(),
        )

    def validate_current(self) -> list[str]:
        value = self.current_settings()
        bundled = (
            self.plugin_dir
            / "templates"
            / "cumulative_displacement_template_v1.qpt"
        )
        errors = validate_batch_settings(value, bundled_template=bundled)
        self._append_log(
            json.dumps(asdict(value), ensure_ascii=False, indent=2)
        )
        if errors:
            self.status_label.setText(
                self.tr("设置检查未通过：{count}项").format(
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
                self.tr("设置通过：将输出{count}期").format(
                    count=len(value.selected_fields)
                )
            )
            self.run_button.setEnabled(True)
            self._append_log(
                self.tr("[PASS] 当前批量设置通过只读检查。")
            )
            self._save_preferences()
        return errors

    def run_batch(self) -> None:
        if self.validate_current():
            return
        self._running = True
        self._cancel_requested = False
        self._last_run_dir = None
        self.progress.setValue(0)
        self._set_busy(True)
        try:
            result = run_displacement_batch(
                self.current_settings(),
                self.plugin_dir,
                progress=self._on_progress,
                is_cancelled=lambda: self._cancel_requested,
            )
            self._last_run_dir = result.run_dir
            self.open_button.setEnabled(True)
            self.status_label.setText(
                self.tr(
                    "完成：{period_count}期，PNG {png_count}，"
                    "PDF {pdf_count}"
                ).format(
                    period_count=result.period_count,
                    png_count=result.png_count,
                    pdf_count=result.pdf_count,
                )
            )
            self._append_log(
                self.tr("[PASS] 输出目录：{path}").format(
                    path=result.run_dir
                )
            )
        except BatchCancelled as exc:
            self.status_label.setText(
                self.tr(
                    "任务已取消；已保留取消状态和临时工作文件，"
                    "重新执行将创建新的任务目录"
                )
            )
            self._append_log(f"[CANCELLED] {exc}")
        except (BatchCoreError, OSError, RuntimeError) as exc:
            self.status_label.setText(
                self.tr("任务失败；请检查质量检查目录")
            )
            self._append_log(f"[FAILED] {exc}")
        finally:
            self._running = False
            self._set_busy(False)

    def request_cancel(self) -> None:
        self._cancel_requested = True
        self.cancel_button.setEnabled(False)
        self.status_label.setText(
            self.tr("已请求取消；将在当前批次后停止")
        )
        self._append_log(self.tr("[取消] 已收到取消请求。"))

    def open_output(self) -> None:
        if self._last_run_dir and self._last_run_dir.is_dir():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._last_run_dir))
            )

    def _on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.status_label.setText(message)
        self._append_log(f"[{value}%] {message}")
        QgsApplication.processEvents()

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.validate_button,
            self.run_button,
            self.scan_button,
            self.select_all_button,
            self.clear_periods_button,
        ):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def _browse_gpkg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择多时相 GeoPackage"),
            "",
            "GeoPackage (*.gpkg)",
        )
        if path:
            self.gpkg_edit.setText(path)
            self.scan_catalog()

    def _browse_basemap(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择卫星底图"),
            "",
            "Raster (*.tif *.tiff *.vrt *.jp2 *.img)",
        )
        if path:
            self.basemap_edit.setText(path)

    def _browse_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择累计形变 QPT 模板"),
            "",
            "QGIS template (*.qpt)",
        )
        if path:
            self.template_edit.setText(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, self.tr("选择输出根目录")
        )
        if path:
            self.output_edit.setText(path)

    def _append_log(self, message: str) -> None:
        self.log.appendPlainText(message)

    def closeEvent(self, event) -> None:
        if self._running:
            self.request_cancel()
            event.ignore()
            return
        self._save_preferences()
        super().closeEvent(event)
