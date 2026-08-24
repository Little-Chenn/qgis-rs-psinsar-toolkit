"""Three-tab M4.0 GUI baseline for the QGIS plugin."""

from __future__ import annotations

import json
from pathlib import Path

from qgis.PyQt.QtCore import QDate, QSettings, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsMapLayerProxyModel,
    QgsProject,
    QgsProviderRegistry,
    QgsVectorLayer,
)
from qgis.gui import QgsMapLayerComboBox

from .builder import BuildCancelled, MapBuildError, build_map
from .settings import (
    BASEMAP_CURRENT_LAYER,
    BASEMAP_LOCAL,
    BASEMAP_NONE,
    DEFAULT_DPI,
    INPUT_CURRENT_LAYER,
    INPUT_GPKG,
    MapJobSettings,
    localized_default_title,
    validate_settings,
)


class ToolkitDialog(QDialog):
    """Collect validated map-generation settings without processing in M4.0."""

    def __init__(self, iface, parent=None, settings_store=None):
        super().__init__(parent)
        self.iface = iface
        self.plugin_dir = Path(__file__).resolve().parent
        self._settings_store = (
            settings_store
            if settings_store is not None
            else QSettings("PyQGISProject", "rs_psinsar_toolkit")
        )
        self._cancel_requested = False
        self._last_run_dir: Path | None = None
        self.setObjectName("rs_psinsar_toolkit_dialog")
        self.setWindowTitle(self.tr("PS-InSAR 垂直形变速率专题制图"))
        self.resize(820, 660)

        intro = QLabel(
            self.tr(
                "本模块使用已完成质量控制的 PS-InSAR 面状网格数据，按指定数值字段生成垂直形变速率专题图，"
                "输出可编辑 QGZ 工程、PNG/PDF 专题图及质量检查报告。每次任务均创建独立输出目录，"
                "不修改输入数据和已有成果。"
            )
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "background:#eaf3ff; border:1px solid #6a9fd4; padding:8px;"
        )
        warning = QLabel(
            self.tr(
                "输入要求：所选图层应为具有有效坐标参考系的面状网格图层，数值字段应表示垂直形变速率，"
                "单位为 mm/年。正值表示垂直向上，负值表示垂直向下。本模块不重新计算形变速率，"
                "也不自动判定异常值及其物理原因。"
            )
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background:#fff4ce; border:1px solid #e0b400; padding:8px;"
        )

        self.tabs = QTabWidget()
        self.tabs.setObjectName("main_tabs")
        self.tabs.addTab(self._build_data_tab(), self.tr("数据与底图"))
        self.tabs.addTab(self._build_layout_tab(), self.tr("专题图设置"))
        self.tabs.addTab(self._build_execution_tab(), self.tr("导出与日志"))

        self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.button_box.button(QDialogButtonBox.Close).setText(self.tr("关闭"))
        self.button_box.rejected.connect(self.close)

        root = QVBoxLayout(self)
        root.addWidget(intro)
        root.addWidget(warning)
        root.addWidget(self.tabs)
        root.addWidget(self.button_box)

        self._connect_signals()
        self._load_preferences()
        self._sync_input_mode()
        self._sync_basemap_mode()
        self._sync_metadata_controls()
        if self.input_mode() == INPUT_GPKG:
            self._populate_gpkg_sublayers()
        else:
            self._populate_value_fields(
                self.vector_layer_combo.currentLayer()
            )
        self._append_log(
            self.tr(
                "PS-InSAR 垂直形变速率专题制图模块已就绪。"
                "请确认数据、底图、专题图设置和导出选项。"
            )
        )

    def _build_data_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        input_group = QGroupBox(self.tr("垂直形变速率数据"))
        input_form = QFormLayout(input_group)
        self.input_mode_combo = QComboBox()
        self.input_mode_combo.setObjectName("input_mode_combo")
        self.input_mode_combo.addItem(self.tr("当前 QGIS 工程图层"), INPUT_CURRENT_LAYER)
        self.input_mode_combo.addItem(self.tr("GeoPackage 文件"), INPUT_GPKG)
        input_form.addRow(self.tr("输入方式："), self.input_mode_combo)

        self.input_stack = QStackedWidget()
        current_page = QWidget()
        current_layout = QFormLayout(current_page)
        self.vector_layer_combo = QgsMapLayerComboBox()
        self.vector_layer_combo.setObjectName("vector_layer_combo")
        self.vector_layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
        current_layout.addRow(self.tr("形变速率图层："), self.vector_layer_combo)
        self.input_stack.addWidget(current_page)

        file_page = QWidget()
        file_layout = QHBoxLayout(file_page)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.vector_path_edit = QLineEdit()
        self.vector_path_edit.setObjectName("vector_path_edit")
        self.vector_path_edit.setPlaceholderText(self.tr("选择包含垂直形变速率网格图层的 GeoPackage"))
        self.vector_browse_button = QPushButton(self.tr("浏览…"))
        self.vector_browse_button.setObjectName("vector_browse_button")
        file_layout.addWidget(self.vector_path_edit)
        file_layout.addWidget(self.vector_browse_button)
        self.input_stack.addWidget(file_page)
        input_form.addRow(self.tr("数据源："), self.input_stack)

        self.vector_sublayer_combo = QComboBox()
        self.vector_sublayer_combo.setObjectName("vector_sublayer_combo")
        self.vector_sublayer_combo.setEditable(False)
        input_form.addRow(self.tr("GeoPackage 图层："), self.vector_sublayer_combo)

        self.value_field_combo = QComboBox()
        self.value_field_combo.setObjectName("value_field_combo")
        self.value_field_combo.setEditable(True)
        input_form.addRow(self.tr("形变速率字段："), self.value_field_combo)

        basemap_group = QGroupBox(self.tr("底图"))
        basemap_form = QFormLayout(basemap_group)
        self.basemap_mode_combo = QComboBox()
        self.basemap_mode_combo.setObjectName("basemap_mode_combo")
        self.basemap_mode_combo.addItem(self.tr("本地栅格底图（推荐）"), BASEMAP_LOCAL)
        self.basemap_mode_combo.addItem(self.tr("当前工程底图图层"), BASEMAP_CURRENT_LAYER)
        self.basemap_mode_combo.addItem(self.tr("不使用底图"), BASEMAP_NONE)
        basemap_form.addRow(self.tr("底图模式："), self.basemap_mode_combo)

        self.basemap_stack = QStackedWidget()
        local_page = QWidget()
        local_layout = QHBoxLayout(local_page)
        local_layout.setContentsMargins(0, 0, 0, 0)
        self.basemap_path_edit = QLineEdit()
        self.basemap_path_edit.setObjectName("basemap_path_edit")
        self.basemap_path_edit.setPlaceholderText(self.tr("选择本地栅格底图"))
        self.basemap_browse_button = QPushButton(self.tr("浏览…"))
        self.basemap_browse_button.setObjectName("basemap_browse_button")
        local_layout.addWidget(self.basemap_path_edit)
        local_layout.addWidget(self.basemap_browse_button)
        self.basemap_stack.addWidget(local_page)

        current_basemap_page = QWidget()
        current_basemap_layout = QFormLayout(current_basemap_page)
        current_basemap_layout.setContentsMargins(0, 0, 0, 0)
        self.basemap_layer_combo = QgsMapLayerComboBox()
        self.basemap_layer_combo.setObjectName("basemap_layer_combo")
        self.basemap_layer_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)
        current_basemap_layout.addRow(self.tr("底图图层："), self.basemap_layer_combo)
        self.basemap_stack.addWidget(current_basemap_page)

        none_page = QWidget()
        none_layout = QVBoxLayout(none_page)
        none_layout.setContentsMargins(0, 0, 0, 0)
        none_layout.addWidget(QLabel(self.tr("将使用白色页面背景，不加载卫星底图。")))
        self.basemap_stack.addWidget(none_page)
        basemap_form.addRow(self.tr("底图来源："), self.basemap_stack)

        output_group = QGroupBox(self.tr("输出位置"))
        output_layout = QHBoxLayout(output_group)
        self.output_root_edit = QLineEdit()
        self.output_root_edit.setObjectName("output_root_edit")
        self.output_root_edit.setPlaceholderText(self.tr("选择输出根目录；任务将自动创建时间戳子目录"))
        self.output_browse_button = QPushButton(self.tr("浏览…"))
        self.output_browse_button.setObjectName("output_browse_button")
        output_layout.addWidget(self.output_root_edit)
        output_layout.addWidget(self.output_browse_button)

        layout.addWidget(input_group)
        layout.addWidget(basemap_group)
        layout.addWidget(output_group)
        layout.addStretch(1)
        return tab

    def _build_layout_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        title_group = QGroupBox(self.tr("标题"))
        title_form = QFormLayout(title_group)
        self.title_edit = QLineEdit(localized_default_title())
        self.title_edit.setObjectName("title_edit")
        title_form.addRow(self.tr("专题图标题："), self.title_edit)

        metadata_group = QGroupBox(self.tr("制图信息"))
        metadata_form = QFormLayout(metadata_group)

        self.show_data_source_checkbox = QCheckBox(self.tr("显示"))
        self.show_data_source_checkbox.setObjectName("show_data_source_checkbox")
        self.show_data_source_checkbox.setChecked(True)
        self.data_source_edit = QLineEdit()
        self.data_source_edit.setObjectName("data_source_edit")
        self.data_source_edit.setPlaceholderText(self.tr("请输入数据来源"))
        data_source_row = QHBoxLayout()
        data_source_row.addWidget(self.show_data_source_checkbox)
        data_source_row.addWidget(self.data_source_edit, 1)
        metadata_form.addRow(self.tr("数据来源："), data_source_row)

        self.show_acquisition_time_checkbox = QCheckBox(self.tr("显示"))
        self.show_acquisition_time_checkbox.setObjectName(
            "show_acquisition_time_checkbox"
        )
        self.show_acquisition_time_checkbox.setChecked(True)
        self.acquisition_time_edit = QLineEdit()
        self.acquisition_time_edit.setObjectName("acquisition_time_edit")
        self.acquisition_time_edit.setPlaceholderText(
            self.tr("例如：2024-01-11—2025-09-11")
        )
        acquisition_row = QHBoxLayout()
        acquisition_row.addWidget(self.show_acquisition_time_checkbox)
        acquisition_row.addWidget(self.acquisition_time_edit, 1)
        metadata_form.addRow(self.tr("数据拍摄时间："), acquisition_row)

        self.show_date_checkbox = QCheckBox(self.tr("显示"))
        self.show_date_checkbox.setObjectName("show_date_checkbox")
        self.show_date_checkbox.setChecked(True)
        self.use_current_date_checkbox = QCheckBox(self.tr("使用当前日期"))
        self.use_current_date_checkbox.setObjectName("use_current_date_checkbox")
        self.use_current_date_checkbox.setChecked(True)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setObjectName("production_date_edit")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        date_row = QHBoxLayout()
        date_row.addWidget(self.show_date_checkbox)
        date_row.addWidget(self.use_current_date_checkbox)
        date_row.addWidget(self.date_edit)
        date_row.addStretch(1)
        metadata_form.addRow(self.tr("制图时间："), date_row)

        self.show_unit_checkbox = QCheckBox(self.tr("显示"))
        self.show_unit_checkbox.setObjectName("show_unit_checkbox")
        self.show_unit_checkbox.setChecked(False)
        self.production_unit_edit = QLineEdit()
        self.production_unit_edit.setObjectName("production_unit_edit")
        self.production_unit_edit.setPlaceholderText(self.tr("请输入制作单位"))
        unit_row = QHBoxLayout()
        unit_row.addWidget(self.show_unit_checkbox)
        unit_row.addWidget(self.production_unit_edit, 1)
        metadata_form.addRow(self.tr("制作单位："), unit_row)

        note = QLabel(
            self.tr(
                "数据来源和数据拍摄时间放在左下角；"
                "制图时间和制作单位位于右下角。"
                "未勾选或未填写的内容不输出，也不保留占位空行。"
            )
        )
        note.setWordWrap(True)

        layout.addWidget(title_group)
        layout.addWidget(metadata_group)
        layout.addWidget(note)
        layout.addStretch(1)
        return tab

    def _build_execution_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        export_group = QGroupBox(self.tr("输出"))
        export_form = QFormLayout(export_group)
        output_types = QHBoxLayout()
        self.export_qgz_checkbox = QCheckBox(self.tr("可编辑 QGZ"))
        self.export_qgz_checkbox.setObjectName("export_qgz_checkbox")
        self.export_qgz_checkbox.setChecked(True)
        self.export_png_checkbox = QCheckBox("PNG")
        self.export_png_checkbox.setObjectName("export_png_checkbox")
        self.export_png_checkbox.setChecked(True)
        self.export_pdf_checkbox = QCheckBox("PDF")
        self.export_pdf_checkbox.setObjectName("export_pdf_checkbox")
        self.export_pdf_checkbox.setChecked(True)
        output_types.addWidget(self.export_qgz_checkbox)
        output_types.addWidget(self.export_png_checkbox)
        output_types.addWidget(self.export_pdf_checkbox)
        output_types.addStretch(1)
        export_form.addRow(self.tr("输出类型："), output_types)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setObjectName("dpi_spin")
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(DEFAULT_DPI)
        self.dpi_spin.setSuffix(" dpi")
        export_form.addRow(self.tr("导出分辨率（DPI）："), self.dpi_spin)

        self.status_label = QLabel(self.tr("请检查当前设置"))
        self.status_label.setObjectName("status_label")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progress_bar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setObjectName("log_edit")
        self.log_edit.setReadOnly(True)

        actions = QHBoxLayout()
        self.validate_button = QPushButton(self.tr("检查当前设置"))
        self.validate_button.setObjectName("validate_button")
        self.run_button = QPushButton(self.tr("生成专题图"))
        self.run_button.setObjectName("run_button")
        self.run_button.setEnabled(False)
        self.cancel_button = QPushButton(self.tr("取消任务"))
        self.cancel_button.setObjectName("cancel_button")
        self.cancel_button.setEnabled(False)
        self.open_output_button = QPushButton(self.tr("打开输出目录"))
        self.open_output_button.setObjectName("open_output_button")
        self.open_output_button.setEnabled(False)
        self.restore_defaults_button = QPushButton(self.tr("恢复默认设置"))
        self.restore_defaults_button.setObjectName("restore_defaults_button")
        self.clear_log_button = QPushButton(self.tr("清空日志"))
        self.clear_log_button.setObjectName("clear_log_button")
        actions.addWidget(self.validate_button)
        actions.addWidget(self.run_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.open_output_button)
        actions.addWidget(self.restore_defaults_button)
        actions.addWidget(self.clear_log_button)
        actions.addStretch(1)

        layout.addWidget(export_group)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_edit, 1)
        layout.addLayout(actions)
        return tab

    def _connect_signals(self) -> None:
        self.input_mode_combo.currentIndexChanged.connect(self._sync_input_mode)
        self.basemap_mode_combo.currentIndexChanged.connect(self._sync_basemap_mode)
        self.vector_layer_combo.layerChanged.connect(self._populate_value_fields)
        self.vector_path_edit.editingFinished.connect(
            self._populate_gpkg_sublayers
        )
        self.vector_sublayer_combo.currentIndexChanged.connect(
            self._populate_gpkg_value_fields
        )
        self.show_data_source_checkbox.toggled.connect(
            self._sync_metadata_controls
        )
        self.show_acquisition_time_checkbox.toggled.connect(
            self._sync_metadata_controls
        )
        self.show_date_checkbox.toggled.connect(self._sync_metadata_controls)
        self.use_current_date_checkbox.toggled.connect(
            self._sync_metadata_controls
        )
        self.show_unit_checkbox.toggled.connect(self._sync_metadata_controls)
        self.vector_browse_button.clicked.connect(self._browse_vector)
        self.basemap_browse_button.clicked.connect(self._browse_basemap)
        self.output_browse_button.clicked.connect(self._browse_output)
        self.validate_button.clicked.connect(self.validate_current_settings)
        self.run_button.clicked.connect(self.run_generation)
        self.cancel_button.clicked.connect(self.request_cancel)
        self.open_output_button.clicked.connect(self.open_last_output)
        self.restore_defaults_button.clicked.connect(self.restore_defaults)
        self.clear_log_button.clicked.connect(self.clear_log)

    @staticmethod
    def _stored_bool(value, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _set_combo_data(combo, value, fallback) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findData(fallback)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_default_values(self) -> None:
        self._set_combo_data(
            self.input_mode_combo,
            INPUT_GPKG,
            INPUT_GPKG,
        )
        self.vector_path_edit.clear()
        self.vector_sublayer_combo.clear()
        self.value_field_combo.clear()
        self.value_field_combo.setEditText("v_median")
        self._set_combo_data(
            self.basemap_mode_combo,
            BASEMAP_LOCAL,
            BASEMAP_LOCAL,
        )
        self.basemap_path_edit.clear()
        self.output_root_edit.clear()
        self.title_edit.setText(localized_default_title())
        self.show_data_source_checkbox.setChecked(True)
        self.data_source_edit.clear()
        self.show_acquisition_time_checkbox.setChecked(True)
        self.acquisition_time_edit.clear()
        self.show_date_checkbox.setChecked(True)
        self.use_current_date_checkbox.setChecked(True)
        self.date_edit.setDate(QDate.currentDate())
        self.show_unit_checkbox.setChecked(False)
        self.production_unit_edit.clear()
        self.export_qgz_checkbox.setChecked(True)
        self.export_png_checkbox.setChecked(True)
        self.export_pdf_checkbox.setChecked(True)
        self.dpi_spin.setValue(DEFAULT_DPI)
        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr("请检查当前设置"))
        self._last_run_dir = None

    def _load_preferences(self) -> None:
        store = self._settings_store
        if not self._stored_bool(store.value("ui/has_saved"), False):
            self._apply_default_values()
            return

        self._set_combo_data(
            self.input_mode_combo,
            store.value("ui/input_mode", INPUT_GPKG),
            INPUT_GPKG,
        )
        self.vector_path_edit.setText(
            str(store.value("ui/vector_path", ""))
        )
        self._set_combo_data(
            self.basemap_mode_combo,
            store.value("ui/basemap_mode", BASEMAP_LOCAL),
            BASEMAP_LOCAL,
        )
        self.basemap_path_edit.setText(
            str(store.value("ui/basemap_path", ""))
        )
        self.output_root_edit.setText(
            str(store.value("ui/output_root", ""))
        )
        self.title_edit.setText(
            str(store.value("ui/title", localized_default_title()))
        )
        self.show_data_source_checkbox.setChecked(
            self._stored_bool(
                store.value("ui/show_data_source"),
                True,
            )
        )
        self.data_source_edit.setText(
            str(store.value("ui/data_source", ""))
        )
        self.show_acquisition_time_checkbox.setChecked(
            self._stored_bool(
                store.value("ui/show_acquisition_time"),
                True,
            )
        )
        self.acquisition_time_edit.setText(
            str(store.value("ui/acquisition_time", ""))
        )
        self.show_date_checkbox.setChecked(
            self._stored_bool(
                store.value("ui/show_production_date"),
                True,
            )
        )
        self.use_current_date_checkbox.setChecked(
            self._stored_bool(
                store.value("ui/use_current_date"),
                True,
            )
        )
        saved_date = QDate.fromString(
            str(
                store.value(
                    "ui/production_date",
                    QDate.currentDate().toString("yyyy-MM-dd"),
                )
            ),
            "yyyy-MM-dd",
        )
        self.date_edit.setDate(
            saved_date if saved_date.isValid() else QDate.currentDate()
        )
        self.show_unit_checkbox.setChecked(
            self._stored_bool(
                store.value("ui/show_production_unit"),
                False,
            )
        )
        self.production_unit_edit.setText(
            str(store.value("ui/production_unit", ""))
        )
        self.export_qgz_checkbox.setChecked(
            self._stored_bool(store.value("ui/export_qgz"), True)
        )
        self.export_png_checkbox.setChecked(
            self._stored_bool(store.value("ui/export_png"), True)
        )
        self.export_pdf_checkbox.setChecked(
            self._stored_bool(store.value("ui/export_pdf"), True)
        )
        try:
            saved_dpi = int(store.value("ui/dpi", DEFAULT_DPI))
        except (TypeError, ValueError):
            saved_dpi = DEFAULT_DPI
        self.dpi_spin.setValue(saved_dpi)

        vector_name = str(store.value("ui/current_vector_name", ""))
        if vector_name:
            for layer in QgsProject.instance().mapLayersByName(vector_name):
                if isinstance(layer, QgsVectorLayer):
                    self.vector_layer_combo.setLayer(layer)
                    break
        basemap_name = str(store.value("ui/current_basemap_name", ""))
        if basemap_name:
            for layer in QgsProject.instance().mapLayersByName(basemap_name):
                if layer.type() == Qgis.LayerType.Raster:
                    self.basemap_layer_combo.setLayer(layer)
                    break

        if self.input_mode() == INPUT_GPKG:
            self._populate_gpkg_sublayers()
            saved_sublayer = str(
                store.value("ui/vector_sublayer", "")
            )
            saved_index = self.vector_sublayer_combo.findText(
                saved_sublayer
            )
            if saved_index >= 0:
                self.vector_sublayer_combo.setCurrentIndex(saved_index)
        saved_field = str(store.value("ui/value_field", "v_median"))
        field_index = self.value_field_combo.findText(saved_field)
        if field_index >= 0:
            self.value_field_combo.setCurrentIndex(field_index)
        else:
            self.value_field_combo.setEditText(saved_field)

    def _save_preferences(self) -> None:
        settings = self.current_settings()
        store = self._settings_store
        values = {
            "has_saved": True,
            "input_mode": settings.input_mode,
            "current_vector_name": settings.current_layer_name,
            "vector_path": settings.vector_path,
            "vector_sublayer": settings.vector_sublayer,
            "value_field": settings.value_field,
            "basemap_mode": settings.basemap_mode,
            "current_basemap_name": settings.current_basemap_name,
            "basemap_path": settings.local_basemap_path,
            "output_root": settings.output_root,
            "title": settings.title,
            "show_data_source": settings.show_data_source,
            "data_source": settings.data_source,
            "show_acquisition_time": settings.show_acquisition_time,
            "acquisition_time": settings.acquisition_time,
            "show_production_date": settings.show_production_date,
            "production_date": settings.production_date,
            "use_current_date": settings.use_current_date,
            "show_production_unit": settings.show_production_unit,
            "production_unit": settings.production_unit,
            "export_qgz": settings.export_qgz,
            "export_png": settings.export_png,
            "export_pdf": settings.export_pdf,
            "dpi": settings.dpi,
        }
        for key, value in values.items():
            store.setValue(f"ui/{key}", value)
        store.sync()

    def restore_defaults(self) -> None:
        self._settings_store.remove("ui")
        self._settings_store.sync()
        self._apply_default_values()
        self._sync_input_mode()
        self._sync_basemap_mode()
        self._sync_metadata_controls()
        self._append_log(self.tr("[设置] 已恢复PS-InSAR专题图默认设置。"))

    def clear_log(self) -> None:
        self.log_edit.clear()

    def closeEvent(self, event) -> None:
        if self.cancel_button.isEnabled():
            self.request_cancel()
            event.ignore()
            return
        self._save_preferences()
        super().closeEvent(event)

    def _sync_input_mode(self) -> None:
        index = 0 if self.input_mode() == INPUT_CURRENT_LAYER else 1
        self.input_stack.setCurrentIndex(index)
        self.vector_sublayer_combo.setVisible(index == 1)

    def _sync_basemap_mode(self) -> None:
        mode_to_index = {
            BASEMAP_LOCAL: 0,
            BASEMAP_CURRENT_LAYER: 1,
            BASEMAP_NONE: 2,
        }
        self.basemap_stack.setCurrentIndex(
            mode_to_index[self.basemap_mode()]
        )

    def _sync_metadata_controls(self) -> None:
        self.data_source_edit.setEnabled(
            self.show_data_source_checkbox.isChecked()
        )
        self.acquisition_time_edit.setEnabled(
            self.show_acquisition_time_checkbox.isChecked()
        )
        show_date = self.show_date_checkbox.isChecked()
        self.use_current_date_checkbox.setEnabled(show_date)
        self.date_edit.setEnabled(
            show_date and not self.use_current_date_checkbox.isChecked()
        )
        if show_date and self.use_current_date_checkbox.isChecked():
            self.date_edit.setDate(QDate.currentDate())
        self.production_unit_edit.setEnabled(
            self.show_unit_checkbox.isChecked()
        )

    def _populate_value_fields(self, layer) -> None:
        previous = self.value_field_combo.currentText().strip()
        self.value_field_combo.clear()
        if layer is not None:
            for field in layer.fields():
                if field.isNumeric():
                    self.value_field_combo.addItem(field.name())
        preferred = "v_median"
        preferred_index = self.value_field_combo.findText(preferred)
        if preferred_index >= 0:
            self.value_field_combo.setCurrentIndex(preferred_index)
        elif previous:
            self.value_field_combo.setEditText(previous)
        elif self.value_field_combo.count() == 0:
            self.value_field_combo.setEditText(preferred)

    def _populate_gpkg_sublayers(self) -> None:
        self.vector_sublayer_combo.clear()
        path = self.vector_path_edit.text().strip()
        if not path:
            return
        details = QgsProviderRegistry.instance().querySublayers(path)
        vector_names = [
            detail.name()
            for detail in details
            if detail.type() == Qgis.LayerType.Vector
        ]
        self.vector_sublayer_combo.addItems(vector_names)
        preferred = self.vector_sublayer_combo.findText("velocity_grid_50m")
        if preferred >= 0:
            self.vector_sublayer_combo.setCurrentIndex(preferred)
        self._populate_gpkg_value_fields()

    def _populate_gpkg_value_fields(self) -> None:
        if self.input_mode() != INPUT_GPKG:
            return
        path = self.vector_path_edit.text().strip()
        sublayer = self.vector_sublayer_combo.currentText().strip()
        if not path or not sublayer:
            return
        layer = QgsVectorLayer(
            f"{path}|layername={sublayer}",
            sublayer,
            "ogr",
        )
        self._populate_value_fields(layer if layer.isValid() else None)

    def input_mode(self) -> str:
        return str(self.input_mode_combo.currentData())

    def basemap_mode(self) -> str:
        return str(self.basemap_mode_combo.currentData())

    def current_settings(self) -> MapJobSettings:
        vector_layer = self.vector_layer_combo.currentLayer()
        basemap_layer = self.basemap_layer_combo.currentLayer()
        if self.use_current_date_checkbox.isChecked():
            self.date_edit.setDate(QDate.currentDate())
        return MapJobSettings(
            input_mode=self.input_mode(),
            current_layer_id=vector_layer.id() if vector_layer else "",
            current_layer_name=vector_layer.name() if vector_layer else "",
            vector_path=self.vector_path_edit.text().strip(),
            vector_sublayer=self.vector_sublayer_combo.currentText().strip(),
            value_field=self.value_field_combo.currentText().strip(),
            basemap_mode=self.basemap_mode(),
            local_basemap_path=self.basemap_path_edit.text().strip(),
            current_basemap_id=basemap_layer.id() if basemap_layer else "",
            current_basemap_name=basemap_layer.name() if basemap_layer else "",
            output_root=self.output_root_edit.text().strip(),
            title=self.title_edit.text().strip(),
            show_data_source=self.show_data_source_checkbox.isChecked(),
            data_source=self.data_source_edit.text().strip(),
            show_acquisition_time=(
                self.show_acquisition_time_checkbox.isChecked()
            ),
            acquisition_time=self.acquisition_time_edit.text().strip(),
            show_production_date=self.show_date_checkbox.isChecked(),
            production_date=self.date_edit.date().toString("yyyy-MM-dd"),
            use_current_date=self.use_current_date_checkbox.isChecked(),
            show_production_unit=self.show_unit_checkbox.isChecked(),
            production_unit=self.production_unit_edit.text().strip(),
            export_qgz=self.export_qgz_checkbox.isChecked(),
            export_png=self.export_png_checkbox.isChecked(),
            export_pdf=self.export_pdf_checkbox.isChecked(),
            dpi=self.dpi_spin.value(),
        )

    def validate_current_settings(self) -> list[str]:
        settings = self.current_settings()
        errors = validate_settings(settings)
        self._append_log(self.tr("设置快照："))
        self._append_log(
            json.dumps(
                settings.__dict__,
                ensure_ascii=False,
                indent=2,
            )
        )
        if errors:
            self.status_label.setText(
                self.tr("设置检查未通过：{count}项").format(count=len(errors))
            )
            self.run_button.setEnabled(False)
            for error in errors:
                self._append_log(self.tr("[需要处理] {error}").format(error=error))
        else:
            self.status_label.setText(self.tr("设置检查通过，可以生成专题图"))
            self.run_button.setEnabled(True)
            self._append_log(self.tr("[PASS] 当前设置通过只读检查。"))
            self._save_preferences()
        return errors

    def run_generation(self) -> None:
        errors = self.validate_current_settings()
        if errors:
            return
        self._cancel_requested = False
        self._last_run_dir = None
        self._set_busy(True)
        self.progress_bar.setValue(0)
        self._append_log(self.tr("开始生成 PS-InSAR 垂直形变速率专题图。"))
        try:
            result = build_map(
                self.current_settings(),
                self.plugin_dir,
                source_project=QgsProject.instance(),
                progress=self._on_build_progress,
                is_cancelled=lambda: self._cancel_requested,
            )
            self._last_run_dir = result.run_dir
            self.open_output_button.setEnabled(True)
            self.status_label.setText(
                self.tr("PS-InSAR 垂直形变速率专题图完成：{status}").format(
                    status=result.status
                )
            )
            self._append_log(
                self.tr("[{status}] 输出目录：{directory}").format(
                    status=result.status, directory=result.run_dir
                )
            )
        except BuildCancelled as exc:
            self.status_label.setText(self.tr("任务已取消，取消记录已写入任务目录"))
            self._append_log(f"[CANCELLED] {exc}")
        except (MapBuildError, OSError, RuntimeError) as exc:
            self.status_label.setText(self.tr("生成失败，请查看日志和失败记录"))
            self._append_log(f"[FAILED] {exc}")
        finally:
            self._set_busy(False)

    def request_cancel(self) -> None:
        self._cancel_requested = True
        self.cancel_button.setEnabled(False)
        self.status_label.setText(self.tr("正在请求取消；将在当前步骤结束后停止"))
        self._append_log(self.tr("[取消] 已收到取消请求。"))

    def open_last_output(self) -> None:
        if self._last_run_dir is not None and self._last_run_dir.is_dir():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._last_run_dir))
            )

    def _on_build_progress(self, value: int, message: str) -> None:
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        self._append_log(f"[{value}%] {message}")
        QgsApplication.processEvents()

    def _set_busy(self, busy: bool) -> None:
        self.validate_button.setEnabled(not busy)
        self.run_button.setEnabled(False if busy else self.run_button.isEnabled())
        self.cancel_button.setEnabled(busy)
        self.restore_defaults_button.setEnabled(not busy)
        self.clear_log_button.setEnabled(not busy)
        self.button_box.setEnabled(not busy)
        if not busy:
            self.cancel_button.setEnabled(False)

    def _browse_vector(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择垂直形变速率 GeoPackage"),
            "",
            "GeoPackage (*.gpkg)",
        )
        if path:
            self.vector_path_edit.setText(path)
            self._populate_gpkg_sublayers()

    def _browse_basemap(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择本地栅格底图"),
            "",
            "Raster (*.tif *.tiff *.vrt *.jp2 *.img)",
        )
        if path:
            self.basemap_path_edit.setText(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.tr("选择输出根目录"))
        if path:
            self.output_root_edit.setText(path)

    def _append_log(self, text: str) -> None:
        self.log_edit.appendPlainText(text)
