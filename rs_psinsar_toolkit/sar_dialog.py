"""M8.4 QGIS dialog and cancellable background SAR task."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication, Qt, QSettings, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QColor, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsApplication,
    QgsColorRampShader,
    QgsCoordinateTransform,
    QgsCsException,
    QgsProject,
    QgsRasterShader,
    QgsRasterLayer,
    QgsSingleBandPseudoColorRenderer,
    QgsTask,
)

from .sar_core import SarCancelled, list_rasters
from .sar_product_catalog import build_catalog, catalog_summary
from .sar_workflow import (
    SarJobResult,
    SarJobSettings,
    execute_sar_job,
    preflight_sar_job,
)


class SarProcessingTask(QgsTask):
    """Run the GDAL SAR workflow outside the QGIS GUI thread."""

    messageChanged = pyqtSignal(str)

    def __init__(self, settings: SarJobSettings, on_finished):
        super().__init__(
            QCoreApplication.translate(
                "SarProcessingDialog", "SAR 影像镶嵌、裁剪与显示增强"
            ),
            QgsTask.CanCancel,
        )
        self.settings = settings
        self.on_finished_callback = on_finished
        self.result_value: SarJobResult | None = None
        self.error_value: Exception | None = None
        self.was_cancelled = False

    def _progress(self, value: int, message: str) -> None:
        self.setProgress(float(value))
        self.messageChanged.emit(message)

    def run(self) -> bool:
        try:
            self.result_value = execute_sar_job(
                self.settings,
                progress=self._progress,
                is_cancelled=self.isCanceled,
            )
            return True
        except SarCancelled:
            self.was_cancelled = True
            return False
        except Exception as exc:
            self.error_value = exc
            return False

    def finished(self, succeeded: bool) -> None:
        self.on_finished_callback(
            succeeded=succeeded,
            result=self.result_value,
            error=self.error_value,
            cancelled=self.was_cancelled or self.isCanceled(),
        )


class SarProcessingDialog(QDialog):
    """Collect explicit source order and safe M8.4 processing settings."""

    def __init__(self, iface, parent=None, settings_store=None):
        super().__init__(parent)
        self.iface = iface
        self._settings_store = (
            settings_store
            if settings_store is not None
            else QSettings("PyQGISProject", "rs_psinsar_toolkit")
        )
        self._task: SarProcessingTask | None = None
        self._last_result: SarJobResult | None = None
        self._resampling_policy_migrated = False
        self._scanned_paths: list[Path] = []
        self._catalog_by_path: dict[str, dict] = {}
        self._radiometric_confirmation_required = False
        self.setObjectName("sar_processing_dialog")
        self.setWindowTitle(self.tr("SAR 影像镶嵌、裁剪与显示增强"))
        self.setMinimumSize(720, 560)
        self.setSizeGripEnabled(True)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(1000, max(720, int(available.width() * 0.78))),
                min(780, max(560, int(available.height() * 0.82))),
            )
        else:
            self.resize(960, 720)

        intro = QLabel(
            self.tr(
                "本模块支持递归扫描 ORG 产品目录，处理单景或多景单波段线性功率 GeoTIFF，"
                "完成覆盖顺序检查、影像镶嵌、掩膜裁剪、线性功率转 dB，以及灰度或伪彩色显示产品生成。"
            )
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "background:#eaf3ff; border:1px solid #6a9fd4; padding:8px;"
        )
        warning = QLabel(
            self.tr(
                "处理约束：多景镶嵌时，列表中靠后的影像以有效像元覆盖靠前影像；升轨与降轨混用、"
                "强度尺度异常需由用户确认。显示增强和外缘羽化仅作用于独立的 8 位显示产品，"
                "不改变线性功率或 dB 成果。本模块不执行自动接缝线、物理辐射平衡或专题图排版。"
            )
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background:#fff4ce; border:1px solid #e0b400; padding:8px;"
        )

        source_group = QGroupBox(self.tr("输入影像与覆盖顺序"))
        source_layout = QVBoxLayout(source_group)
        folder_row = QHBoxLayout()
        self.input_folder_edit = QLineEdit()
        self.input_folder_edit.setObjectName("sar_input_folder_edit")
        self.input_folder_edit.setPlaceholderText(
            self.tr("选择ORG总目录、产品目录或包含GeoTIFF的文件夹")
        )
        self.input_folder_button = QPushButton(self.tr("浏览…"))
        self.scan_button = QPushButton(self.tr("扫描 GeoTIFF"))
        folder_row.addWidget(self.input_folder_edit, 1)
        folder_row.addWidget(self.input_folder_button)
        folder_row.addWidget(self.scan_button)
        source_layout.addLayout(folder_row)

        self.raster_list = QListWidget()
        self.raster_list.setObjectName("sar_raster_order_list")
        self.raster_list.setMinimumHeight(110)
        self.raster_list.setMaximumHeight(160)
        self.raster_list.setToolTip(
            self.tr("从上到下依次处理；列表后面的有效像元覆盖前面的有效像元。")
        )
        order_buttons = QVBoxLayout()
        self.move_up_button = QPushButton(self.tr("上移"))
        self.move_down_button = QPushButton(self.tr("下移"))
        self.keep_ascending_button = QPushButton(self.tr("仅保留升轨"))
        self.keep_descending_button = QPushButton(self.tr("仅保留降轨"))
        self.restore_scan_button = QPushButton(self.tr("恢复全部"))
        self.keep_ascending_button.setEnabled(False)
        self.keep_descending_button.setEnabled(False)
        self.restore_scan_button.setEnabled(False)
        order_buttons.addWidget(self.move_up_button)
        order_buttons.addWidget(self.move_down_button)
        order_buttons.addSpacing(8)
        order_buttons.addWidget(self.keep_ascending_button)
        order_buttons.addWidget(self.keep_descending_button)
        order_buttons.addWidget(self.restore_scan_button)
        order_buttons.addStretch(1)
        order_row = QHBoxLayout()
        order_row.addWidget(self.raster_list, 1)
        order_row.addLayout(order_buttons)
        source_layout.addLayout(order_row)

        paths_group = QGroupBox(self.tr("裁剪与输出"))
        paths_form = QFormLayout(paths_group)
        mask_row = QHBoxLayout()
        self.mask_edit = QLineEdit()
        self.mask_edit.setObjectName("sar_mask_edit")
        self.mask_edit.setPlaceholderText(self.tr("选择Polygon/MultiPolygon裁剪面"))
        self.mask_button = QPushButton(self.tr("浏览…"))
        mask_row.addWidget(self.mask_edit, 1)
        mask_row.addWidget(self.mask_button)
        paths_form.addRow(self.tr("裁剪面："), mask_row)

        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setObjectName("sar_output_edit")
        self.output_edit.setPlaceholderText(
            self.tr("选择输出根目录；任务将自动创建时间戳子目录")
        )
        self.output_button = QPushButton(self.tr("浏览…"))
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.output_button)
        paths_form.addRow(self.tr("输出根目录："), output_row)

        parameters_group = QGroupBox(self.tr("处理参数"))
        parameters_form = QFormLayout(parameters_group)
        resolution_row = QGridLayout()
        self.x_resolution_spin = self._resolution_spin()
        self.x_resolution_spin.setObjectName("sar_x_resolution_spin")
        self.y_resolution_spin = self._resolution_spin()
        self.y_resolution_spin.setObjectName("sar_y_resolution_spin")
        resolution_row.addWidget(QLabel(self.tr("X 方向")), 0, 0)
        resolution_row.addWidget(self.x_resolution_spin, 0, 1)
        resolution_row.addWidget(QLabel(self.tr("Y 方向")), 0, 2)
        resolution_row.addWidget(self.y_resolution_spin, 0, 3)
        resolution_row.setColumnStretch(1, 1)
        resolution_row.setColumnStretch(3, 1)
        parameters_form.addRow(self.tr("目标像元大小："), resolution_row)

        self.mosaic_resampling_combo = self._resampling_combo(
            "near"
        )
        self.mosaic_resampling_combo.setObjectName(
            "sar_mosaic_resampling_combo"
        )
        parameters_form.addRow(
            self.tr("镶嵌重采样："),
            self.mosaic_resampling_combo,
        )
        self.clip_resampling_combo = self._resampling_combo("near")
        self.clip_resampling_combo.setObjectName(
            "sar_clip_resampling_combo"
        )
        parameters_form.addRow(
            self.tr("裁剪重采样："),
            self.clip_resampling_combo,
        )

        stretch_row = QGridLayout()
        self.stretch_low_spin = QDoubleSpinBox()
        self.stretch_low_spin.setRange(0.0, 99.9)
        self.stretch_low_spin.setDecimals(1)
        self.stretch_low_spin.setValue(2.0)
        self.stretch_low_spin.setSuffix(" %")
        self.stretch_high_spin = QDoubleSpinBox()
        self.stretch_high_spin.setRange(0.1, 100.0)
        self.stretch_high_spin.setDecimals(1)
        self.stretch_high_spin.setValue(98.0)
        self.stretch_high_spin.setSuffix(" %")
        stretch_row.addWidget(QLabel(self.tr("低值")), 0, 0)
        stretch_row.addWidget(self.stretch_low_spin, 0, 1)
        stretch_row.addWidget(QLabel(self.tr("高值")), 0, 2)
        stretch_row.addWidget(self.stretch_high_spin, 0, 3)
        stretch_row.setColumnStretch(1, 1)
        stretch_row.setColumnStretch(3, 1)
        parameters_form.addRow(self.tr("百分位范围："), stretch_row)

        display_group = QGroupBox(self.tr("显示增强与外缘羽化"))
        display_form = QFormLayout(display_group)
        self.display_method_combo = QComboBox()
        self.display_method_combo.setObjectName("sar_display_method_combo")
        self.display_method_combo.addItem(self.tr("2%—98%累计百分比拉伸"), "percentile")
        self.display_method_combo.addItem(self.tr("最小值—最大值拉伸"), "minmax")
        self.display_method_combo.addItem(self.tr("均值—标准差拉伸"), "stddev")
        self.display_method_combo.addItem(self.tr("直方图均衡化"), "equalize")
        self.display_method_combo.addItem(self.tr("均值居中的8位归一化"), "centered")
        display_form.addRow(self.tr("增强方法："), self.display_method_combo)

        adjustment_row = QGridLayout()
        self.brightness_spin = QSpinBox()
        self.brightness_spin.setRange(-100, 100)
        self.brightness_spin.setValue(0)
        self.contrast_spin = QSpinBox()
        self.contrast_spin.setRange(-99, 99)
        self.contrast_spin.setValue(0)
        self.gamma_spin = QDoubleSpinBox()
        self.gamma_spin.setRange(0.10, 10.0)
        self.gamma_spin.setDecimals(2)
        self.gamma_spin.setValue(1.0)
        self.brightness_spin.setToolTip(self.tr("整体增亮或压暗 8 位显示产品。"))
        self.contrast_spin.setToolTip(self.tr("扩大或压缩明暗差异。"))
        self.gamma_spin.setToolTip(self.tr("调整中间亮度层次；1.00 表示不调整。"))
        adjustment_row.addWidget(QLabel(self.tr("亮度")), 0, 0)
        adjustment_row.addWidget(self.brightness_spin, 0, 1)
        adjustment_row.addWidget(QLabel(self.tr("对比度")), 0, 2)
        adjustment_row.addWidget(self.contrast_spin, 0, 3)
        adjustment_row.addWidget(QLabel("Gamma"), 0, 4)
        adjustment_row.addWidget(self.gamma_spin, 0, 5)
        adjustment_row.setColumnStretch(1, 1)
        adjustment_row.setColumnStretch(3, 1)
        adjustment_row.setColumnStretch(5, 1)
        display_form.addRow(self.tr("亮度与层次调整："), adjustment_row)

        colour_row = QGridLayout()
        self.color_mode_combo = QComboBox()
        self.color_mode_combo.addItem(self.tr("灰度"), "grayscale")
        self.color_mode_combo.addItem(self.tr("单波段伪彩色"), "pseudocolor")
        self.color_ramp_combo = QComboBox()
        self.color_ramp_combo.addItem("Viridis", "viridis")
        self.color_ramp_combo.addItem("Spectral", "spectral")
        self.color_ramp_combo.addItem("Terrain", "terrain")
        self.color_ramp_combo.addItem("Plasma", "plasma")
        colour_row.addWidget(QLabel(self.tr("显示模式")), 0, 0)
        colour_row.addWidget(self.color_mode_combo, 0, 1)
        colour_row.addWidget(QLabel(self.tr("色带")), 0, 2)
        colour_row.addWidget(self.color_ramp_combo, 0, 3)
        colour_row.setColumnStretch(1, 1)
        colour_row.setColumnStretch(3, 1)
        display_form.addRow(self.tr("颜色设置："), colour_row)

        self.feather_spin = QSpinBox()
        self.feather_spin.setRange(0, 1000)
        self.feather_spin.setValue(0)
        self.feather_spin.setSuffix(self.tr(" 像素"))
        self.feather_spin.setSpecialValueText(self.tr("关闭"))
        self.feather_spin.setToolTip(
            self.tr("仅淡化8位显示产品的有效数据外缘；不生成seamline，不改变科学栅格。")
        )
        feather_row = QHBoxLayout()
        feather_row.addWidget(self.feather_spin, 1)
        feather_row.addWidget(QLabel(self.tr("0 表示关闭")))
        display_form.addRow(self.tr("外缘羽化："), feather_row)
        self.create_display_checkbox = QCheckBox(
            self.tr("生成独立的 RGBA 8 位显示产品")
        )
        self.create_display_checkbox.setChecked(True)
        display_form.addRow("", self.create_display_checkbox)

        self.linear_power_checkbox, linear_power_row = self._wrapped_checkbox(
            self.tr("我确认输入为非负线性功率数据，可执行 10 × log10 转换。"),
            "sar_linear_power_acknowledgement",
        )
        self.source_order_checkbox, source_order_row = self._wrapped_checkbox(
            self.tr("我确认影像覆盖顺序正确，并了解后列影像覆盖前列影像。"),
            "sar_source_order_acknowledgement",
        )
        self.mixed_orbit_checkbox, mixed_orbit_row = self._wrapped_checkbox(
            self.tr("我确认需要混合升轨与降轨影像，并了解其几何和强度差异。"),
            "sar_mixed_orbit_acknowledgement",
        )
        self.radiometric_warning_checkbox, radiometric_warning_row = self._wrapped_checkbox(
            self.tr("我已检查影像间的强度尺度异常，并决定保留当前输入。"),
            "sar_radiometric_warning_acknowledgement",
        )
        self.cubic_resampling_checkbox, cubic_resampling_row = self._wrapped_checkbox(
            self.tr("我确认使用三次卷积，并了解其可能产生非正功率像元。"),
            "sar_cubic_resampling_acknowledgement",
        )
        self.load_result_checkbox, load_result_row = self._wrapped_checkbox(
            self.tr("完成后将结果加载至当前 QGIS 工程，优先加载 8 位显示产品。"),
            "sar_load_result_checkbox",
            checked=True,
        )

        acknowledgements_group = QGroupBox(self.tr("科学语义与操作确认"))
        acknowledgements_group.setObjectName("sar_acknowledgements_group")
        acknowledgements_layout = QVBoxLayout(acknowledgements_group)
        acknowledgement_rows = (
            linear_power_row,
            source_order_row,
            mixed_orbit_row,
            radiometric_warning_row,
            cubic_resampling_row,
            load_result_row,
        )
        for row in acknowledgement_rows:
            acknowledgements_layout.addWidget(row)
        acknowledgements_layout.addStretch(1)

        self.status_label = QLabel(self.tr("请选择或扫描输入影像，并检查当前设置"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(72)
        self.log_edit.setMaximumHeight(110)

        actions = QHBoxLayout()
        self.validate_button = QPushButton(self.tr("检查当前设置"))
        self.run_button = QPushButton(self.tr("开始影像处理"))
        self.run_button.setEnabled(False)
        self.cancel_button = QPushButton(self.tr("取消任务"))
        self.cancel_button.setEnabled(False)
        self.open_button = QPushButton(self.tr("打开输出目录"))
        self.open_button.setEnabled(False)
        self.clear_log_button = QPushButton(self.tr("清空日志"))
        actions.addWidget(self.validate_button)
        actions.addWidget(self.run_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.open_button)
        actions.addWidget(self.clear_log_button)
        actions.addStretch(1)

        section_tabs = QTabWidget()
        section_tabs.setObjectName("sar_section_tabs")
        section_tabs.addTab(
            self._scroll_page(
                "sar_inputs_scroll_area",
                intro,
                warning,
                source_group,
                paths_group,
            ),
            self.tr("输入与顺序"),
        )
        section_tabs.addTab(
            self._scroll_page(
                "sar_processing_scroll_area",
                parameters_group,
                display_group,
            ),
            self.tr("处理与显示"),
        )
        section_tabs.addTab(
            self._scroll_page(
                "sar_confirmations_scroll_area",
                acknowledgements_group,
            ),
            self.tr("科学确认"),
        )

        root = QVBoxLayout(self)
        root.addWidget(section_tabs, 1)
        root.addWidget(self.status_label)
        root.addWidget(self.progress_bar)
        root.addWidget(self.log_edit)
        root.addLayout(actions)

        self.input_folder_button.clicked.connect(self._browse_input)
        self.scan_button.clicked.connect(self.scan_folder)
        self.move_up_button.clicked.connect(lambda: self._move_item(-1))
        self.move_down_button.clicked.connect(lambda: self._move_item(1))
        self.keep_ascending_button.clicked.connect(
            lambda: self._filter_orbit("ASCENDING")
        )
        self.keep_descending_button.clicked.connect(
            lambda: self._filter_orbit("DESCENDING")
        )
        self.restore_scan_button.clicked.connect(self._restore_scanned_paths)
        self.mask_button.clicked.connect(self._browse_mask)
        self.output_button.clicked.connect(self._browse_output)
        self.validate_button.clicked.connect(self.validate_current_settings)
        self.run_button.clicked.connect(self.start_task)
        self.cancel_button.clicked.connect(self.cancel_task)
        self.open_button.clicked.connect(self.open_output)
        self.clear_log_button.clicked.connect(self.log_edit.clear)
        self.input_folder_edit.textChanged.connect(
            self._folder_changed
        )
        self.mask_edit.textChanged.connect(self._invalidate_validation)
        self.output_edit.textChanged.connect(self._invalidate_validation)
        self.x_resolution_spin.valueChanged.connect(
            self._invalidate_validation
        )
        self.y_resolution_spin.valueChanged.connect(
            self._invalidate_validation
        )
        self.mosaic_resampling_combo.currentIndexChanged.connect(
            self._invalidate_validation
        )
        self.clip_resampling_combo.currentIndexChanged.connect(
            self._invalidate_validation
        )
        self.stretch_low_spin.valueChanged.connect(
            self._invalidate_validation
        )
        self.stretch_high_spin.valueChanged.connect(
            self._invalidate_validation
        )
        for combo in (
            self.display_method_combo,
            self.color_mode_combo,
            self.color_ramp_combo,
        ):
            combo.currentIndexChanged.connect(self._invalidate_validation)
        for spin in (
            self.brightness_spin,
            self.contrast_spin,
            self.gamma_spin,
            self.feather_spin,
        ):
            spin.valueChanged.connect(self._invalidate_validation)
        self.create_display_checkbox.toggled.connect(self._invalidate_validation)
        self.create_display_checkbox.toggled.connect(self._sync_display_controls)
        self.linear_power_checkbox.toggled.connect(
            self._invalidate_validation
        )
        self.source_order_checkbox.toggled.connect(
            self._invalidate_validation
        )
        self.mixed_orbit_checkbox.toggled.connect(
            self._invalidate_validation
        )
        self.radiometric_warning_checkbox.toggled.connect(
            self._invalidate_validation
        )
        self.cubic_resampling_checkbox.toggled.connect(
            self._invalidate_validation
        )
        self._load_preferences()
        self.display_method_combo.currentIndexChanged.connect(
            self._sync_display_controls
        )
        self.color_mode_combo.currentIndexChanged.connect(
            self._sync_display_controls
        )
        self.mosaic_resampling_combo.currentIndexChanged.connect(
            self._sync_confirmation_controls
        )
        self.clip_resampling_combo.currentIndexChanged.connect(
            self._sync_confirmation_controls
        )
        self._sync_display_controls()
        self._sync_confirmation_controls()
        self._append_log(
            self.tr("SAR 影像处理模块已就绪。请选择或扫描输入影像，并检查影像覆盖顺序。")
        )
        if self._resampling_policy_migrated:
            self._append_log(
                self.tr(
                    "[安全设置] 已把旧重采样偏好迁移为最近邻；"
                    "如重新选择三次卷积，必须显式确认风险。"
                )
            )

    @staticmethod
    def _scroll_page(object_name: str, *widgets: QWidget) -> QWidget:
        """Build one compact, resizable section page for small displays."""

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName(object_name)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        for widget in widgets:
            layout.addWidget(widget)
        layout.addStretch(1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    @staticmethod
    def _wrapped_checkbox(
        text: str,
        object_name: str,
        checked: bool = False,
    ) -> tuple[QCheckBox, QWidget]:
        """Keep long confirmation text readable without widening the dialog."""

        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        checkbox = QCheckBox()
        checkbox.setObjectName(object_name)
        checkbox.setChecked(checked)
        checkbox.setAccessibleName(text)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setBuddy(checkbox)
        row.addWidget(checkbox, 0, Qt.AlignTop)
        row.addWidget(label, 1)
        return checkbox, container

    def _resolution_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1_000_000.0)
        spin.setDecimals(6)
        spin.setValue(0.0)
        spin.setSpecialValueText(self.tr("自动"))
        return spin

    def _resampling_combo(self, default: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem(self.tr("最近邻"), "near")
        combo.addItem(self.tr("双线性"), "bilinear")
        combo.addItem(self.tr("三次卷积"), "cubic")
        index = combo.findData(default)
        combo.setCurrentIndex(index)
        return combo

    def _load_preferences(self) -> None:
        store = self._settings_store
        self.input_folder_edit.setText(
            str(store.value("sar/input_folder", ""))
        )
        self.mask_edit.setText(str(store.value("sar/mask_path", "")))
        self.output_edit.setText(
            str(store.value("sar/output_root", ""))
        )
        policy_version = str(
            store.value("sar/resampling_policy_version", "")
        )
        if policy_version != "m83.1":
            self._resampling_policy_migrated = True
            store.setValue("sar/mosaic_resampling", "near")
            store.setValue("sar/clip_resampling", "near")
            store.setValue("sar/resampling_policy_version", "m83.1")
        for combo, key, fallback in (
            (
                self.mosaic_resampling_combo,
                "sar/mosaic_resampling",
                "near",
            ),
            (
                self.clip_resampling_combo,
                "sar/clip_resampling",
                "near",
            ),
        ):
            index = combo.findData(str(store.value(key, fallback)))
            combo.setCurrentIndex(index if index >= 0 else 0)
        try:
            self.stretch_low_spin.setValue(
                float(store.value("sar/stretch_low", 2.0))
            )
            self.stretch_high_spin.setValue(
                float(store.value("sar/stretch_high", 98.0))
            )
        except (TypeError, ValueError):
            self.stretch_low_spin.setValue(2.0)
            self.stretch_high_spin.setValue(98.0)
        for combo, key, fallback in (
            (self.display_method_combo, "sar/display_method", "percentile"),
            (self.color_mode_combo, "sar/color_mode", "grayscale"),
            (self.color_ramp_combo, "sar/color_ramp", "viridis"),
        ):
            index = combo.findData(str(store.value(key, fallback)))
            combo.setCurrentIndex(index if index >= 0 else 0)
        try:
            self.brightness_spin.setValue(int(store.value("sar/brightness", 0)))
            self.contrast_spin.setValue(int(store.value("sar/contrast", 0)))
            self.gamma_spin.setValue(float(store.value("sar/gamma", 1.0)))
            self.feather_spin.setValue(int(store.value("sar/feather_pixels", 0)))
        except (TypeError, ValueError):
            self.brightness_spin.setValue(0)
            self.contrast_spin.setValue(0)
            self.gamma_spin.setValue(1.0)
            self.feather_spin.setValue(0)
        self.create_display_checkbox.setChecked(
            str(store.value("sar/create_display_product", "true")).lower()
            in {"1", "true", "yes"}
        )
        self.load_result_checkbox.setChecked(
            str(store.value("sar/load_result", "true")).lower()
            in {"1", "true", "yes"}
        )
        self.linear_power_checkbox.setChecked(False)
        self.source_order_checkbox.setChecked(False)
        self.mixed_orbit_checkbox.setChecked(False)
        self.radiometric_warning_checkbox.setChecked(False)
        self.cubic_resampling_checkbox.setChecked(False)

    def _save_preferences(self) -> None:
        store = self._settings_store
        store.setValue(
            "sar/input_folder",
            self.input_folder_edit.text().strip(),
        )
        store.setValue("sar/mask_path", self.mask_edit.text().strip())
        store.setValue("sar/output_root", self.output_edit.text().strip())
        store.setValue(
            "sar/mosaic_resampling",
            self.mosaic_resampling_combo.currentData(),
        )
        store.setValue(
            "sar/clip_resampling",
            self.clip_resampling_combo.currentData(),
        )
        store.setValue("sar/resampling_policy_version", "m83.1")
        store.setValue("sar/stretch_low", self.stretch_low_spin.value())
        store.setValue(
            "sar/stretch_high",
            self.stretch_high_spin.value(),
        )
        store.setValue("sar/display_method", self.display_method_combo.currentData())
        store.setValue("sar/brightness", self.brightness_spin.value())
        store.setValue("sar/contrast", self.contrast_spin.value())
        store.setValue("sar/gamma", self.gamma_spin.value())
        store.setValue("sar/color_mode", self.color_mode_combo.currentData())
        store.setValue("sar/color_ramp", self.color_ramp_combo.currentData())
        store.setValue("sar/feather_pixels", self.feather_spin.value())
        store.setValue(
            "sar/create_display_product", self.create_display_checkbox.isChecked()
        )
        store.setValue(
            "sar/load_result",
            self.load_result_checkbox.isChecked(),
        )
        store.sync()

    def _browse_input(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择SAR GeoTIFF文件夹"),
            self.input_folder_edit.text().strip(),
        )
        if path:
            self.input_folder_edit.setText(path)

    def _browse_mask(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择裁剪面"),
            self.mask_edit.text().strip(),
            (
                self.tr("矢量裁剪面 (*.gpkg *.shp *.geojson);;")
                + self.tr("所有文件 (*.*)")
            ),
        )
        if path:
            self.mask_edit.setText(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择输出根目录"),
            self.output_edit.text().strip(),
        )
        if path:
            self.output_edit.setText(path)

    def _folder_changed(self) -> None:
        if self._task is None:
            self.raster_list.clear()
            self._scanned_paths = []
            self._catalog_by_path = {}
            self._radiometric_confirmation_required = False
            self._update_orbit_filter_buttons()
            self._sync_confirmation_controls()
        self._invalidate_validation()

    def scan_folder(self) -> None:
        self.raster_list.clear()
        try:
            paths = list_rasters(self.input_folder_edit.text().strip())
        except Exception as exc:
            self.status_label.setText(self.tr("扫描失败"))
            self._append_log(self.tr("[拒绝] {error}").format(error=exc))
            return
        catalog = build_catalog(paths)
        self._scanned_paths = list(paths)
        self._catalog_by_path = {
            str(Path(item["raster"]).resolve()): item
            for item in catalog
        }
        self._set_raster_paths(paths)
        self._update_orbit_filter_buttons()
        self._sync_confirmation_controls()
        summary = catalog_summary(catalog)
        self.status_label.setText(
            self.tr("已扫描{count}幅影像，请检查顺序").format(count=len(paths))
        )
        self._append_log(self.tr("[输入顺序]"))
        for index, path in enumerate(paths, start=1):
            self._append_log(f"  {index}. {path.name}")
        self._append_log(
            self.tr(
                "[ORG目录识别] 产品{product_count}景 | 任务标识{families} | "
                "元数据任务{missions} | 极化{polarisations} | 轨道{directions}"
            ).format(
                product_count=summary["product_count"],
                families=",".join(summary["folder_product_families"]) or self.tr("未知"),
                missions=",".join(summary["mission_ids"]) or self.tr("未知"),
                polarisations=",".join(summary["polarisations"]) or self.tr("未知"),
                directions=",".join(summary["pass_directions"]) or self.tr("未知"),
            )
        )
        for index, item in enumerate(catalog, start=1):
            self._append_log(
                self.tr(
                    "  {index}. {date} | {orbit} | 入射角{angle} | 伴随文件{completeness}"
                ).format(
                    index=index,
                    date=item.get("start_time") or self.tr("日期未知"),
                    orbit=item.get("pass_direction") or self.tr("轨道未知"),
                    angle=item.get("incidence_angle_mid_swath"),
                    completeness=(
                        self.tr("完整")
                        if item.get("companion_complete")
                        else self.tr("不完整")
                    ),
                )
            )
        self._invalidate_validation()

    def _set_raster_paths(self, paths: list[Path]) -> None:
        self.raster_list.clear()
        for path in paths:
            self.raster_list.addItem(str(path))
        self._sync_confirmation_controls()

    def _update_orbit_filter_buttons(self) -> None:
        directions = {
            str(item.get("pass_direction") or "").upper()
            for item in self._catalog_by_path.values()
        }
        self.keep_ascending_button.setEnabled("ASCENDING" in directions)
        self.keep_descending_button.setEnabled("DESCENDING" in directions)
        self.restore_scan_button.setEnabled(bool(self._scanned_paths))

    def _filter_orbit(self, direction: str) -> None:
        selected = [
            path
            for path in self._scanned_paths
            if str(
                self._catalog_by_path.get(
                    str(path.resolve()), {}
                ).get("pass_direction")
                or ""
            ).upper()
            == direction
        ]
        if not selected:
            self._append_log(
                self.tr("[轨向筛选] 未发现{direction}产品。").format(
                    direction=direction
                )
            )
            return
        self._set_raster_paths(selected)
        label = self.tr("升轨") if direction == "ASCENDING" else self.tr("降轨")
        self.status_label.setText(
            self.tr("已保留{orbit}{count}景，请检查顺序").format(
                orbit=label, count=len(selected)
            )
        )
        self._append_log(
            self.tr(
                "[轨向筛选] 已保留{orbit}{count}景；未复制、移动或修改源数据。"
            ).format(orbit=label, count=len(selected))
        )
        self.source_order_checkbox.setChecked(False)
        self.mixed_orbit_checkbox.setChecked(False)
        self._invalidate_validation()

    def _restore_scanned_paths(self) -> None:
        if not self._scanned_paths:
            return
        self._set_raster_paths(self._scanned_paths)
        self.status_label.setText(
            self.tr("已恢复全部{count}景，请检查顺序").format(
                count=len(self._scanned_paths)
            )
        )
        self._append_log(
            self.tr("[轨向筛选] 已恢复扫描结果全部{count}景。").format(
                count=len(self._scanned_paths)
            )
        )
        self.source_order_checkbox.setChecked(False)
        self.mixed_orbit_checkbox.setChecked(False)
        self._invalidate_validation()

    def _move_item(self, offset: int) -> None:
        row = self.raster_list.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.raster_list.count():
            return
        item = self.raster_list.takeItem(row)
        self.raster_list.insertItem(target, item)
        self.raster_list.setCurrentRow(target)
        self.source_order_checkbox.setChecked(False)
        self._invalidate_validation()

    def _sync_display_controls(self, *_args) -> None:
        enabled = self.create_display_checkbox.isChecked()
        percentile_enabled = (
            enabled and self.display_method_combo.currentData() == "percentile"
        )
        for widget in (
            self.display_method_combo,
            self.brightness_spin,
            self.contrast_spin,
            self.gamma_spin,
            self.color_mode_combo,
            self.feather_spin,
        ):
            widget.setEnabled(enabled and self._task is None)
        self.stretch_low_spin.setEnabled(percentile_enabled and self._task is None)
        self.stretch_high_spin.setEnabled(percentile_enabled and self._task is None)
        self.color_ramp_combo.setEnabled(
            enabled
            and self.color_mode_combo.currentData() == "pseudocolor"
            and self._task is None
        )

    def _selected_orbit_directions(self) -> set[str]:
        directions: set[str] = set()
        for index in range(self.raster_list.count()):
            path = str(Path(self.raster_list.item(index).text()).resolve())
            direction = str(
                self._catalog_by_path.get(path, {}).get("pass_direction") or ""
            ).upper()
            if direction:
                directions.add(direction)
        return directions

    def _sync_confirmation_controls(self, *_args) -> None:
        if self._task is not None:
            return
        multiple = self.raster_list.count() > 1
        self.source_order_checkbox.setEnabled(multiple)
        if not multiple:
            self.source_order_checkbox.setChecked(False)
        mixed = len(self._selected_orbit_directions()) > 1
        self.mixed_orbit_checkbox.setEnabled(mixed)
        if not mixed:
            self.mixed_orbit_checkbox.setChecked(False)
        self.radiometric_warning_checkbox.setEnabled(
            self._radiometric_confirmation_required
        )
        if not self._radiometric_confirmation_required:
            self.radiometric_warning_checkbox.setChecked(False)
        cubic = "cubic" in {
            self.mosaic_resampling_combo.currentData(),
            self.clip_resampling_combo.currentData(),
        }
        self.cubic_resampling_checkbox.setEnabled(cubic)
        if not cubic:
            self.cubic_resampling_checkbox.setChecked(False)

    def current_settings(self) -> SarJobSettings:
        return SarJobSettings(
            raster_paths=tuple(
                self.raster_list.item(index).text()
                for index in range(self.raster_list.count())
            ),
            mask_path=self.mask_edit.text().strip(),
            output_root=self.output_edit.text().strip(),
            x_resolution=self.x_resolution_spin.value(),
            y_resolution=self.y_resolution_spin.value(),
            mosaic_resampling=str(
                self.mosaic_resampling_combo.currentData()
            ),
            clip_resampling=str(
                self.clip_resampling_combo.currentData()
            ),
            stretch_low=self.stretch_low_spin.value(),
            stretch_high=self.stretch_high_spin.value(),
            display_method=str(self.display_method_combo.currentData()),
            brightness=int(self.brightness_spin.value()),
            contrast=int(self.contrast_spin.value()),
            gamma=float(self.gamma_spin.value()),
            color_mode=str(self.color_mode_combo.currentData()),
            color_ramp=str(self.color_ramp_combo.currentData()),
            create_display_product=self.create_display_checkbox.isChecked(),
            feather_pixels=int(self.feather_spin.value()),
            acknowledge_linear_power=(
                self.linear_power_checkbox.isChecked()
            ),
            acknowledge_source_order=(
                self.source_order_checkbox.isChecked()
            ),
            acknowledge_mixed_orbits=(
                self.mixed_orbit_checkbox.isChecked()
            ),
            acknowledge_radiometric_warnings=(
                self.radiometric_warning_checkbox.isChecked()
            ),
            acknowledge_cubic_resampling=(
                self.cubic_resampling_checkbox.isChecked()
            ),
        )

    def _invalidate_validation(self) -> None:
        if self._task is None:
            self.run_button.setEnabled(False)
            self.status_label.setText(self.tr("设置已改变，请重新检查"))

    def validate_current_settings(self) -> dict:
        self.status_label.setText(self.tr("正在只读检查输入……"))
        result = preflight_sar_job(self.current_settings())
        if result["status"] != "PASS":
            errors_text = " ".join(str(error) for error in result["errors"])
            if self.tr("组间中位强度异常") in errors_text:
                self._radiometric_confirmation_required = True
            self._sync_confirmation_controls()
            self.status_label.setText(self.tr("输入检查未通过"))
            self.run_button.setEnabled(False)
            for error in result["errors"]:
                self._append_log(self.tr("[拒绝] {error}").format(error=error))
            return result
        inspection = result["inspection"]
        resolved = result["resolved_parameters"]
        self.status_label.setText(self.tr("输入检查通过，可以开始"))
        self.run_button.setEnabled(True)
        self._append_log(
            self.tr("[通过] {count}幅 | {crs} | {x_resolution}×{y_resolution}").format(
                count=inspection["raster_count"],
                crs=inspection["crs"],
                x_resolution=resolved["x_resolution"],
                y_resolution=resolved["y_resolution"],
            )
        )
        for item in inspection["rasters"]:
            self._append_log(
                self.tr("  {order}. {file} | 正值比例 {ratio:.6f}").format(
                    order=item["source_order"],
                    file=item["file"],
                    ratio=item["sample_positive_ratio"],
                )
            )
        for warning in result.get("warnings", []):
            self._append_log(
                self.tr("[科学预检警告] {warning}").format(warning=warning)
            )
        estimate = resolved["mask_limited_grid_estimate"]
        self._append_log(
            self.tr(
                "[资源估算] 掩膜包络网格 {width}×{height}，"
                "三阶段未压缩约{size_gib:.3f} GiB"
            ).format(
                width=estimate["width"],
                height=estimate["height"],
                size_gib=estimate["three_stage_uncompressed_gib"],
            )
        )
        return result

    def start_task(self) -> None:
        if self._task is not None:
            return
        checked = self.validate_current_settings()
        if checked["status"] != "PASS":
            return
        self._save_preferences()
        self._last_result = None
        self.progress_bar.setValue(0)
        self.open_button.setEnabled(False)
        self._set_busy(True)
        self.status_label.setText(self.tr("影像处理任务运行中"))
        task = SarProcessingTask(
            self.current_settings(),
            self._task_finished,
        )
        task.messageChanged.connect(self._append_log)
        task.progressChanged.connect(
            lambda value: self.progress_bar.setValue(int(value))
        )
        self._task = task
        QgsApplication.taskManager().addTask(task)

    def cancel_task(self) -> None:
        if self._task is None:
            return
        self.cancel_button.setEnabled(False)
        self.status_label.setText(self.tr("正在取消……"))
        self._append_log(self.tr("[取消] 已发出请求，将在安全检查点停止。"))
        self._task.cancel()

    def _task_finished(
        self,
        *,
        succeeded: bool,
        result: SarJobResult | None,
        error: Exception | None,
        cancelled: bool,
    ) -> None:
        self._task = None
        self._set_busy(False)
        if succeeded and result is not None:
            self._last_result = result
            self.progress_bar.setValue(100)
            self.status_label.setText(self.tr("影像处理完成：PASS"))
            self.open_button.setEnabled(True)
            self._append_log(
                self.tr("[完成] {run_dir}").format(run_dir=result.run_dir)
            )
            self._append_log(
                self.tr("[显示范围] {minimum:.6f} — {maximum:.6f} dB").format(
                    minimum=result.display_min, maximum=result.display_max
                )
            )
            if self.load_result_checkbox.isChecked():
                try:
                    self._load_db_result(result)
                except Exception as exc:
                    self._append_log(
                        self.tr("[加载结果失败] {error}").format(error=exc)
                    )
            return
        self.run_button.setEnabled(False)
        if cancelled:
            self.status_label.setText(self.tr("影像处理任务已取消"))
            self._append_log(
                self.tr("[已取消] 任务目录保留取消记录，不作为正式成果。")
            )
        else:
            self.status_label.setText(self.tr("影像处理任务失败"))
            self._append_log(
                self.tr("[失败] {error_type}：{error}").format(
                    error_type=type(error).__name__ if error else "Error",
                    error=error or self.tr("未知错误"),
                )
            )

    def _load_db_result(self, result: SarJobResult) -> None:
        run_label = result.run_dir.name.split("_sar_", 1)[0]
        display_raster = str(result.artifacts.get("display_raster") or "")
        use_display_product = bool(display_raster) and Path(display_raster).is_file()
        layer = QgsRasterLayer(
            display_raster if use_display_product else result.artifacts["db_raster"],
            (
                self.tr("SAR显示增强结果（8位，仅用于显示）— {run_label}").format(
                    run_label=run_label
                )
                if use_display_product
                else self.tr("SAR镶嵌裁剪结果（dB）— {run_label}").format(
                    run_label=run_label
                )
            ),
            "gdal",
        )
        if not layer.isValid():
            raise ValueError(self.tr("QGIS无法加载SAR处理结果。"))
        minimum = float(result.display_min)
        maximum = float(result.display_max)
        if not use_display_product:
            midpoint = (minimum + maximum) / 2.0
            color_ramp = QgsColorRampShader()
            color_ramp.setMinimumValue(minimum)
            color_ramp.setMaximumValue(maximum)
            color_ramp.setColorRampType(QgsColorRampShader.Interpolated)
            color_ramp.setColorRampItemList(
                [
                    QgsColorRampShader.ColorRampItem(
                        minimum, QColor(32, 32, 32), f"{minimum:.3f} dB"
                    ),
                    QgsColorRampShader.ColorRampItem(
                        midpoint, QColor(128, 128, 128), f"{midpoint:.3f} dB"
                    ),
                    QgsColorRampShader.ColorRampItem(
                        maximum, QColor(224, 224, 224), f"{maximum:.3f} dB"
                    ),
                ]
            )
            raster_shader = QgsRasterShader()
            raster_shader.setRasterShaderFunction(color_ramp)
            renderer = QgsSingleBandPseudoColorRenderer(
                layer.dataProvider(), 1, raster_shader
            )
            layer.setRenderer(renderer)
        layer.setCustomProperty("rs_psinsar/display_min_db", minimum)
        layer.setCustomProperty("rs_psinsar/display_max_db", maximum)
        layer.setCustomProperty(
            "rs_psinsar/display_style",
            "rgba_8bit_display_product" if use_display_product else "soft_grayscale_32_224",
        )

        project = QgsProject.instance()
        project.addMapLayer(layer)
        self.iface.setActiveLayer(layer)
        canvas = self.iface.mapCanvas()
        extent = layer.extent()
        destination_crs = canvas.mapSettings().destinationCrs()
        try:
            if (
                layer.crs().isValid()
                and destination_crs.isValid()
                and layer.crs() != destination_crs
            ):
                transform = QgsCoordinateTransform(
                    layer.crs(),
                    destination_crs,
                    project.transformContext(),
                )
                extent = transform.transformBoundingBox(extent)
            if not extent.isEmpty():
                extent.scale(1.05)
                canvas.setExtent(extent)
            else:
                self.iface.zoomToActiveLayer()
        except QgsCsException as exc:
            self._append_log(
                self.tr(
                    "[QGIS] 自动坐标转换缩放失败，改用QGIS活动图层缩放：{error}"
                ).format(error=exc)
            )
            self.iface.zoomToActiveLayer()
        canvas.refresh()
        self._append_log(
            self.tr("[QGIS] 已加载{product}并按工程坐标系缩放；未清空现有图层。").format(
                product=(
                    self.tr("8位显示产品")
                    if use_display_product
                    else self.tr("Float32 dB结果")
                )
            )
        )

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.input_folder_edit,
            self.input_folder_button,
            self.scan_button,
            self.raster_list,
            self.move_up_button,
            self.move_down_button,
            self.keep_ascending_button,
            self.keep_descending_button,
            self.restore_scan_button,
            self.mask_edit,
            self.mask_button,
            self.output_edit,
            self.output_button,
            self.x_resolution_spin,
            self.y_resolution_spin,
            self.mosaic_resampling_combo,
            self.clip_resampling_combo,
            self.stretch_low_spin,
            self.stretch_high_spin,
            self.display_method_combo,
            self.brightness_spin,
            self.contrast_spin,
            self.gamma_spin,
            self.color_mode_combo,
            self.color_ramp_combo,
            self.feather_spin,
            self.create_display_checkbox,
            self.linear_power_checkbox,
            self.source_order_checkbox,
            self.mixed_orbit_checkbox,
            self.radiometric_warning_checkbox,
            self.cubic_resampling_checkbox,
            self.validate_button,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self._update_orbit_filter_buttons()
            self._sync_display_controls()
            self._sync_confirmation_controls()
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(busy)

    def open_output(self) -> None:
        if self._last_result is not None:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._last_result.run_dir))
            )

    def _append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(str(message))

    def closeEvent(self, event) -> None:
        if self._task is not None:
            self.cancel_task()
            event.ignore()
            return
        self._save_preferences()
        super().closeEvent(event)
