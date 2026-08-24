"""QGIS dialog for real geometric correction and the retained teaching demo."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from qgis.PyQt.QtCore import QCoreApplication, Qt, QSettings, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsApplication, QgsTask

from .geometry_core import GeometryCancelled
from .geometry_real_workflow import (
    RealGeometryJobResult,
    RealGeometryJobSettings,
    execute_real_geometry_job,
    preflight_real_geometry_input,
)
from .geometry_workflow import (
    GeometryJobResult,
    GeometryJobSettings,
    execute_geometry_job,
    preflight_geometry_input,
)


GeometrySettings = Union[RealGeometryJobSettings, GeometryJobSettings]
GeometryResult = Union[RealGeometryJobResult, GeometryJobResult]


class GeometryCorrectionTask(QgsTask):
    """Run either geometry workflow away from the QGIS GUI thread."""

    messageChanged = pyqtSignal(str)

    def __init__(self, mode: str, settings: GeometrySettings, on_finished):
        title = (
            QCoreApplication.translate(
                "GeometryCorrectionDialog",
                "GCP 几何校正与独立精度检查",
            )
            if mode == "real"
            else QCoreApplication.translate(
                "GeometryCorrectionDialog",
                "几何校正流程验证",
            )
        )
        super().__init__(title, QgsTask.CanCancel)
        self.mode = mode
        self.settings = settings
        self.on_finished_callback = on_finished
        self.result_value: GeometryResult | None = None
        self.error_value: Exception | None = None
        self.was_cancelled = False

    def _progress(self, value: int, message: str) -> None:
        self.setProgress(float(value))
        self.messageChanged.emit(message)

    def run(self) -> bool:
        try:
            if self.mode == "real":
                self.result_value = execute_real_geometry_job(
                    self.settings,  # type: ignore[arg-type]
                    progress=self._progress,
                    is_cancelled=self.isCanceled,
                )
            else:
                self.result_value = execute_geometry_job(
                    self.settings,  # type: ignore[arg-type]
                    progress=self._progress,
                    is_cancelled=self.isCanceled,
                )
            return True
        except GeometryCancelled:
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
            mode=self.mode,
        )


class GeometryCorrectionDialog(QDialog):
    """Collect settings for real correction or the reproducible teaching demo."""

    def __init__(self, iface, parent=None, settings_store=None):
        super().__init__(parent)
        self.iface = iface
        self._settings_store = (
            settings_store
            if settings_store is not None
            else QSettings("PyQGISProject", "rs_psinsar_toolkit")
        )
        self._task: GeometryCorrectionTask | None = None
        self._last_run_dir: Path | None = None
        self._last_real_output: Path | None = None
        self.setObjectName("geometry_correction_dialog")
        self.setWindowTitle(self.tr("GCP 几何校正与精度检查"))
        self.setMinimumSize(720, 560)
        self.setSizeGripEnabled(True)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(1000, max(720, int(available.width() * 0.78))),
                min(800, max(560, int(available.height() * 0.82))),
            )
        else:
            self.resize(900, 720)

        intro = QLabel(
            self.tr(
                "本模块包含“GCP 几何校正”和“流程验证”两种模式。GCP 几何校正使用外部训练控制点"
                "完成影像到地图坐标的校正，并通过独立检查点评估精度；流程验证仅用于检查控制点读取、"
                "变换计算、RMSE 统计和报告输出。所有任务均创建独立输出目录，不修改输入数据。"
            )
        )
        intro.setObjectName("geometry_mode_intro")
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "background:#eaf3ff; border:1px solid #6a9fd4; padding:8px;"
        )

        self.tabs = QTabWidget()
        self.tabs.setObjectName("geometry_mode_tabs")
        self.tabs.addTab(self._build_real_page(), self.tr("GCP 几何校正"))
        self.tabs.addTab(self._build_teaching_page(), self.tr("流程验证"))

        self.status_label = QLabel(self.tr("请填写参数并检查当前设置"))
        self.status_label.setObjectName("geometry_status_label")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("geometry_progress_bar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setObjectName("geometry_log_edit")
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(72)
        self.log_edit.setMaximumHeight(120)

        actions = QHBoxLayout()
        self.validate_button = QPushButton(self.tr("检查当前设置"))
        self.validate_button.setObjectName("geometry_validate_button")
        self.run_button = QPushButton(self.tr("开始几何校正"))
        self.run_button.setObjectName("geometry_run_button")
        self.run_button.setEnabled(False)
        self.cancel_button = QPushButton(self.tr("取消任务"))
        self.cancel_button.setObjectName("geometry_cancel_button")
        self.cancel_button.setEnabled(False)
        self.open_button = QPushButton(self.tr("打开输出目录"))
        self.open_button.setObjectName("geometry_open_button")
        self.open_button.setEnabled(False)
        self.clear_log_button = QPushButton(self.tr("清空日志"))
        actions.addWidget(self.validate_button)
        actions.addWidget(self.run_button)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.open_button)
        actions.addWidget(self.clear_log_button)
        actions.addStretch(1)

        root = QVBoxLayout(self)
        root.addWidget(intro)
        root.addWidget(self.tabs)
        root.addWidget(self.status_label)
        root.addWidget(self.progress_bar)
        root.addWidget(self.log_edit, 1)
        root.addLayout(actions)

        self.validate_button.clicked.connect(self.validate_input)
        self.run_button.clicked.connect(self.start_task)
        self.cancel_button.clicked.connect(self.cancel_task)
        self.open_button.clicked.connect(self.open_output)
        self.clear_log_button.clicked.connect(self.log_edit.clear)
        self.tabs.currentChanged.connect(self._mode_changed)
        self._connect_invalidation_signals()
        self._load_preferences()
        self._mode_changed(self.tabs.currentIndex())
        self._append_log(
            self.tr(
                "GCP 几何校正模块已就绪。请选择待校正影像、训练 GCP、独立检查点和输出目录，"
                "然后检查当前设置。"
            )
        )

    def _build_real_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("real_geometry_scroll_area")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        warning = QLabel(
            self.tr(
                "适用范围：本模式基于外部 GCP 执行影像到地图坐标的几何校正，支持一阶仿射、"
                "二阶/三阶多项式和薄板样条（TPS），并使用独立检查点评估 RMSE。"
                "本模式不使用 SAR 轨道、传感器模型或 DEM，不属于 Range-Doppler 地形校正。"
            )
        )
        warning.setObjectName("real_geometry_warning")
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background:#fff4ce; border:1px solid #e0b400; padding:8px;"
        )
        layout.addWidget(warning)

        group = QGroupBox(self.tr("GCP 几何校正输入"))
        form = QFormLayout(group)
        self.real_source_edit, self.real_source_button, source_row = self._path_row(
            "real_geometry_source_edit",
            self.tr("选择待校正 PNG、TIFF 或其他 GDAL 栅格"),
        )
        form.addRow(self.tr("待校正影像："), source_row)
        self.real_train_edit, self.real_train_button, train_row = self._path_row(
            "real_geometry_train_edit",
            self.tr("选择训练 GCP CSV 或 QGIS Georeferencer .points 文件"),
        )
        form.addRow(self.tr("训练GCP："), train_row)
        self.real_check_edit, self.real_check_button, check_row = self._path_row(
            "real_geometry_check_edit",
            self.tr("选择独立检查点 CSV 或 .points 文件"),
        )
        form.addRow(self.tr("独立检查点："), check_row)
        self.real_output_edit, self.real_output_button, output_row = self._path_row(
            "real_geometry_output_edit",
            self.tr("选择输出根目录；任务将自动创建时间戳子目录"),
        )
        form.addRow(self.tr("输出根目录："), output_row)

        self.real_target_crs_edit = QLineEdit("EPSG:32650")
        self.real_target_crs_edit.setObjectName("real_geometry_target_crs_edit")
        self.real_target_crs_edit.setPlaceholderText(self.tr("例如 EPSG:32650"))
        form.addRow(self.tr("目标坐标参考系（CRS）："), self.real_target_crs_edit)

        self.real_model_combo = QComboBox()
        self.real_model_combo.setObjectName("real_geometry_model_combo")
        self.real_model_combo.addItem(self.tr("一阶仿射"), "affine")
        self.real_model_combo.addItem(self.tr("二阶多项式"), "polynomial2")
        self.real_model_combo.addItem(self.tr("三阶多项式"), "polynomial3")
        self.real_model_combo.addItem(self.tr("薄板样条（TPS）"), "tps")
        form.addRow(self.tr("变换模型："), self.real_model_combo)

        resolution_row = QHBoxLayout()
        self.real_x_resolution = self._resolution_spin()
        self.real_y_resolution = self._resolution_spin()
        resolution_row.addWidget(QLabel("X"))
        resolution_row.addWidget(self.real_x_resolution)
        resolution_row.addWidget(QLabel("Y"))
        resolution_row.addWidget(self.real_y_resolution)
        form.addRow(self.tr("输出像元大小："), resolution_row)

        self.real_resampling_combo = QComboBox()
        self.real_resampling_combo.setObjectName("real_geometry_resampling_combo")
        self.real_resampling_combo.addItem(self.tr("双线性（连续影像推荐）"), "bilinear")
        self.real_resampling_combo.addItem(self.tr("最近邻（分类影像）"), "near")
        self.real_resampling_combo.addItem(self.tr("三次卷积（平滑影像）"), "cubic")
        form.addRow(self.tr("重采样："), self.real_resampling_combo)

        self.real_threshold_spin = QDoubleSpinBox()
        self.real_threshold_spin.setObjectName("real_geometry_threshold_spin")
        self.real_threshold_spin.setRange(0.0, 1000000.0)
        self.real_threshold_spin.setDecimals(4)
        self.real_threshold_spin.setSingleStep(0.1)
        self.real_threshold_spin.setValue(0.0)
        self.real_threshold_spin.setSpecialValueText(self.tr("仅报告，人工判定"))
        form.addRow(self.tr("独立检查点 RMSE 阈值（像素）："), self.real_threshold_spin)

        self.real_ack_checkbox, acknowledgement_row = self._wrapped_checkbox(
            self.tr(
                "我确认训练 GCP 与独立检查点来自外部参考，且两组点相互独立；"
                "并了解本功能不执行基于 SAR 轨道与 DEM 的地形校正。"
            ),
            "real_geometry_ack_checkbox",
        )
        form.addRow("", acknowledgement_row)
        self.real_load_checkbox = QCheckBox(
            self.tr("完成后加载校正 GeoTIFF，并缩放至结果图层范围")
        )
        self.real_load_checkbox.setObjectName("real_geometry_load_checkbox")
        self.real_load_checkbox.setChecked(True)
        form.addRow("", self.real_load_checkbox)

        hint = QLabel(
            self.tr(
                "支持标准 CSV（point_id、pixel、line、x、y）及 QGIS Georeferencer .points 文件。"
                "pixel/line 采用左上角为原点的 GDAL 像素坐标。"
            )
        )
        hint.setObjectName("real_geometry_csv_hint")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555;")
        hint_row = QVBoxLayout()
        hint_row.addWidget(hint)
        self.real_template_button = QPushButton(self.tr("导出标准GCP CSV空模板…"))
        self.real_template_button.setObjectName("real_geometry_template_button")
        hint_row.addWidget(self.real_template_button)
        form.addRow(self.tr("控制点格式："), hint_row)
        layout.addWidget(group)

        self.real_source_button.clicked.connect(self._browse_real_source)
        self.real_train_button.clicked.connect(
            lambda: self._browse_point_file(self.real_train_edit, self.tr("选择训练GCP"))
        )
        self.real_check_button.clicked.connect(
            lambda: self._browse_point_file(self.real_check_edit, self.tr("选择独立检查点"))
        )
        self.real_output_button.clicked.connect(
            lambda: self._browse_directory(
                self.real_output_edit,
                self.tr("选择几何校正输出根目录"),
            )
        )
        self.real_template_button.clicked.connect(self._export_point_template)
        layout.addStretch(1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    def _build_teaching_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("teaching_geometry_scroll_area")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        warning = QLabel(
            self.tr(
                "本页根据参考 GeoTIFF 的 GeoTransform 自动构造控制点，用于验证控制点读取、"
                "变换计算、独立检查、RMSE 统计和报告输出流程。由于控制点由参考影像自身信息生成，"
                "所得近零误差不能代表真实影像的校正精度。"
            )
        )
        warning.setObjectName("teaching_mode_warning")
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background:#f2f2f2; border:1px solid #999; padding:8px;"
        )
        layout.addWidget(warning)
        group = QGroupBox(self.tr("流程验证输入"))
        form = QFormLayout(group)

        self.source_edit, self.source_button, source_row = self._path_row(
            "geometry_source_edit",
            self.tr("选择单波段Byte、EPSG:4326参考GeoTIFF"),
        )
        form.addRow(self.tr("参考GeoTIFF："), source_row)
        self.output_edit, self.output_button, output_row = self._path_row(
            "geometry_output_edit",
            self.tr("选择输出根目录；任务将自动创建时间戳子目录"),
        )
        form.addRow(self.tr("输出根目录："), output_row)
        self.resampling_combo = QComboBox()
        self.resampling_combo.setObjectName("geometry_resampling_combo")
        self.resampling_combo.addItem(self.tr("双线性（教学基线）"), "bilinear")
        self.resampling_combo.addItem(self.tr("最近邻"), "near")
        self.resampling_combo.addItem(self.tr("三次卷积"), "cubic")
        form.addRow(self.tr("重采样："), self.resampling_combo)
        self.acknowledge_checkbox = QCheckBox(
            self.tr(
                "我已了解：控制点由参考 GeoTIFF 的 GeoTransform 自动构造，本页仅用于流程验证。"
            )
        )
        self.acknowledge_checkbox.setObjectName("geometry_acknowledge_checkbox")
        form.addRow("", self.acknowledge_checkbox)
        layout.addWidget(group)
        layout.addStretch(1)

        self.source_button.clicked.connect(self._browse_teaching_source)
        self.output_button.clicked.connect(
            lambda: self._browse_directory(
                self.output_edit,
                self.tr("选择流程验证输出根目录"),
            )
        )
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    @staticmethod
    def _wrapped_checkbox(
        text: str,
        object_name: str,
        checked: bool = False,
    ) -> tuple[QCheckBox, QWidget]:
        """Keep long acknowledgements readable without forcing a wide dialog."""

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

    def _path_row(self, object_name: str, placeholder: str):
        edit = QLineEdit()
        edit.setObjectName(object_name)
        edit.setPlaceholderText(placeholder)
        button = QPushButton(self.tr("浏览…"))
        button.setObjectName(f"{object_name}_button")
        row = QHBoxLayout()
        row.addWidget(edit, 1)
        row.addWidget(button)
        return edit, button, row

    def _resolution_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 10000000.0)
        spin.setDecimals(6)
        spin.setSingleStep(1.0)
        spin.setValue(0.0)
        spin.setSpecialValueText(self.tr("自动"))
        return spin

    def _connect_invalidation_signals(self) -> None:
        edits = [
            self.real_source_edit,
            self.real_train_edit,
            self.real_check_edit,
            self.real_output_edit,
            self.real_target_crs_edit,
            self.source_edit,
            self.output_edit,
        ]
        for edit in edits:
            edit.textChanged.connect(self._invalidate_validation)
        combos = [
            self.real_model_combo,
            self.real_resampling_combo,
            self.resampling_combo,
        ]
        for combo in combos:
            combo.currentIndexChanged.connect(self._invalidate_validation)
        for spin in (
            self.real_x_resolution,
            self.real_y_resolution,
            self.real_threshold_spin,
        ):
            spin.valueChanged.connect(self._invalidate_validation)
        self.real_ack_checkbox.toggled.connect(self._invalidate_validation)
        self.acknowledge_checkbox.toggled.connect(self._invalidate_validation)

    def _load_preferences(self) -> None:
        value = self._settings_store.value
        self.real_source_edit.setText(str(value("geometry/real/source_path", "")))
        self.real_train_edit.setText(str(value("geometry/real/train_path", "")))
        self.real_check_edit.setText(str(value("geometry/real/check_path", "")))
        self.real_output_edit.setText(str(value("geometry/real/output_root", "")))
        self.real_target_crs_edit.setText(
            str(value("geometry/real/target_crs", "EPSG:32650"))
        )
        real_resampling = str(value("geometry/real/resampling", "bilinear"))
        index = self.real_resampling_combo.findData(real_resampling)
        self.real_resampling_combo.setCurrentIndex(index if index >= 0 else 0)
        real_model = str(value("geometry/real/transform_model", "affine"))
        index = self.real_model_combo.findData(real_model)
        self.real_model_combo.setCurrentIndex(index if index >= 0 else 0)
        self.real_x_resolution.setValue(
            float(value("geometry/real/x_resolution", 0.0))
        )
        self.real_y_resolution.setValue(
            float(value("geometry/real/y_resolution", 0.0))
        )
        self.real_threshold_spin.setValue(
            float(value("geometry/real/threshold_pixel", 0.0))
        )
        self.real_load_checkbox.setChecked(
            str(value("geometry/real/load_result", "true")).lower()
            not in {"false", "0"}
        )

        self.source_edit.setText(str(value("geometry/source_path", "")))
        self.output_edit.setText(str(value("geometry/output_root", "")))
        teaching_resampling = str(value("geometry/resampling", "bilinear"))
        index = self.resampling_combo.findData(teaching_resampling)
        self.resampling_combo.setCurrentIndex(index if index >= 0 else 0)
        self.real_ack_checkbox.setChecked(False)
        self.acknowledge_checkbox.setChecked(False)

    def _save_preferences(self) -> None:
        real = self.current_real_settings()
        teaching = self.current_teaching_settings()
        values = {
            "geometry/real/source_path": real.source_path,
            "geometry/real/train_path": real.training_points_path,
            "geometry/real/check_path": real.check_points_path,
            "geometry/real/output_root": real.output_root,
            "geometry/real/target_crs": real.target_crs,
            "geometry/real/resampling": real.resampling,
            "geometry/real/transform_model": real.transform_model,
            "geometry/real/x_resolution": real.x_resolution,
            "geometry/real/y_resolution": real.y_resolution,
            "geometry/real/threshold_pixel": real.check_rmse_threshold_pixel,
            "geometry/real/load_result": real.load_result,
            "geometry/source_path": teaching.source_path,
            "geometry/output_root": teaching.output_root,
            "geometry/resampling": teaching.resampling,
        }
        for key, value in values.items():
            self._settings_store.setValue(key, value)
        self._settings_store.sync()

    def _browse_real_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择待校正原始影像"),
            self.real_source_edit.text().strip(),
            self.tr("栅格影像 (*.tif *.tiff *.png *.jpg *.jpeg *.img);;所有文件 (*)"),
        )
        if path:
            self.real_source_edit.setText(path)

    def _browse_teaching_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择教学参考GeoTIFF"),
            self.source_edit.text().strip(),
            "GeoTIFF (*.tif *.tiff)",
        )
        if path:
            self.source_edit.setText(path)

    def _browse_point_file(self, edit: QLineEdit, title: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            edit.text().strip(),
            self.tr("控制点文件 (*.csv *.points);;所有文件 (*)"),
        )
        if path:
            edit.setText(path)

    def _browse_directory(self, edit: QLineEdit, title: str) -> None:
        path = QFileDialog.getExistingDirectory(self, title, edit.text().strip())
        if path:
            edit.setText(path)

    def _export_point_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("导出标准GCP CSV空模板"),
            "gcp_template.csv",
            "CSV (*.csv)",
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".csv":
            target = target.with_suffix(".csv")
        try:
            target.write_text("point_id,pixel,line,x,y\n", encoding="utf-8-sig")
        except OSError as exc:
            self.status_label.setText(self.tr("GCP模板导出失败"))
            self._append_log(
                self.tr("[失败] 无法导出GCP模板：{error}").format(error=exc)
            )
            return
        self._append_log(
            self.tr("[模板] 已导出标准GCP CSV空模板：{path}").format(
                path=target
            )
        )

    def current_real_settings(self) -> RealGeometryJobSettings:
        return RealGeometryJobSettings(
            source_path=self.real_source_edit.text().strip(),
            training_points_path=self.real_train_edit.text().strip(),
            check_points_path=self.real_check_edit.text().strip(),
            output_root=self.real_output_edit.text().strip(),
            target_crs=self.real_target_crs_edit.text().strip(),
            transform_model=str(self.real_model_combo.currentData()),
            resampling=str(self.real_resampling_combo.currentData()),
            x_resolution=float(self.real_x_resolution.value()),
            y_resolution=float(self.real_y_resolution.value()),
            check_rmse_threshold_pixel=float(self.real_threshold_spin.value()),
            acknowledge_external_points=self.real_ack_checkbox.isChecked(),
            load_result=self.real_load_checkbox.isChecked(),
        )

    def current_teaching_settings(self) -> GeometryJobSettings:
        return GeometryJobSettings(
            source_path=self.source_edit.text().strip(),
            output_root=self.output_edit.text().strip(),
            resampling=str(self.resampling_combo.currentData()),
            acknowledge_teaching_mode=self.acknowledge_checkbox.isChecked(),
        )

    def current_settings(self) -> GeometrySettings:
        return (
            self.current_real_settings()
            if self.tabs.currentIndex() == 0
            else self.current_teaching_settings()
        )

    def _mode_changed(self, _index: int) -> None:
        self.run_button.setText(
            self.tr("开始几何校正")
            if self.tabs.currentIndex() == 0
            else self.tr("开始流程验证")
        )
        self._invalidate_validation()

    def _invalidate_validation(self) -> None:
        if self._task is None:
            self.run_button.setEnabled(False)
            self.status_label.setText(self.tr("输入已改变，请重新检查"))

    def validate_input(self) -> dict:
        if self.tabs.currentIndex() == 0:
            result = preflight_real_geometry_input(self.current_real_settings())
            mode_name = self.tr("GCP 几何校正")
        else:
            result = preflight_geometry_input(self.current_teaching_settings())
            mode_name = self.tr("流程验证")
        if result["status"] != "PASS":
            self.status_label.setText(self.tr("输入检查未通过"))
            self.run_button.setEnabled(False)
            for error in result["errors"]:
                self._append_log(
                    self.tr("[拒绝] {error}").format(error=error)
                )
            return result

        info = result["input"]
        self.status_label.setText(self.tr("输入检查通过，可以开始"))
        self.run_button.setEnabled(True)
        self._append_log(
            self.tr(
                "[通过/{mode}] {width}×{height} | {band_type} | 原坐标系={crs}"
            ).format(
                mode=mode_name,
                width=info["width"],
                height=info["height"],
                band_type=info["band_type"],
                crs=info["crs"] or self.tr("无/未知"),
            )
        )
        for warning in result.get("warnings", []):
            self._append_log(
                self.tr("[提醒] {warning}").format(warning=warning)
            )
        if self.tabs.currentIndex() == 0:
            train_count = result["training_points"]["enabled_point_count"]
            check_count = result["check_points"]["enabled_point_count"]
            self._append_log(
                self.tr(
                    "[控制点] 训练GCP={train_count}；独立检查点={check_count}；"
                    "目标坐标系={target_crs}。"
                ).format(
                    train_count=train_count,
                    check_count=check_count,
                    target_crs=result["target_crs"],
                )
            )
        else:
            self._append_log(
                self.tr(
                    "[限制] 控制点地图坐标来自参考GeoTransform，"
                    "RMSE 仅用于验证计算和报告流程。"
                )
            )
        return result

    def start_task(self) -> None:
        if self._task is not None:
            return
        result = self.validate_input()
        if result["status"] != "PASS":
            return
        self._save_preferences()
        self.progress_bar.setValue(0)
        self._last_run_dir = None
        self._last_real_output = None
        self.open_button.setEnabled(False)
        self._set_busy(True)
        self.status_label.setText(self.tr("任务运行中"))
        mode = "real" if self.tabs.currentIndex() == 0 else "teaching"
        self._append_log(self.tr("[开始] 正在创建独立任务目录。"))
        task = GeometryCorrectionTask(mode, self.current_settings(), self._task_finished)
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
        self._append_log(
            self.tr("[取消] 已发出取消请求，当前安全检查点后停止。")
        )
        self._task.cancel()

    def _task_finished(
        self,
        *,
        succeeded: bool,
        result: GeometryResult | None,
        error: Exception | None,
        cancelled: bool,
        mode: str,
    ) -> None:
        self._task = None
        self._set_busy(False)
        if succeeded and result is not None:
            self.progress_bar.setValue(100)
            self._last_run_dir = result.run_dir
            self.open_button.setEnabled(True)
            if isinstance(result, RealGeometryJobResult):
                self.status_label.setText(
                    self.tr("几何校正完成：{status}").format(
                        status=result.status
                    )
                )
                self._last_real_output = result.output_path
                self._append_log(
                    self.tr("[完成] {run_dir}").format(run_dir=result.run_dir)
                )
                self._append_log(
                    self.tr(
                        "[独立检查] RMSE={rmse:.6f}像素；"
                        "最大误差={maximum:.6f}像素。"
                    ).format(
                        rmse=result.check_rmse_pixel,
                        maximum=result.check_max_error_pixel,
                    )
                )
                if self.current_real_settings().load_result:
                    self._load_real_output(result.output_path)
            else:
                self.status_label.setText(self.tr("流程验证完成：PASS"))
                self._append_log(
                    self.tr("[完成] {run_dir}").format(run_dir=result.run_dir)
                )
                self._append_log(
                    self.tr(
                        "[独立检查/流程验证] RMSE={rmse:.12g}像素；"
                        "最大误差={maximum:.12g}像素。"
                    ).format(
                        rmse=result.check_rmse_pixel,
                        maximum=result.check_max_error_pixel,
                    )
                )
            return

        self.run_button.setEnabled(False)
        if cancelled:
            self.status_label.setText(self.tr("任务已取消"))
            self._append_log(
                self.tr("[已取消] 任务目录保留取消记录，不作为正式成果。")
            )
        else:
            self.status_label.setText(self.tr("任务失败"))
            self._append_log(
                self.tr("[失败/{mode}] {error_type}：{error}").format(
                    mode=mode,
                    error_type=type(error).__name__ if error else "Error",
                    error=error or self.tr("未知错误"),
                )
            )

    def _load_real_output(self, output_path: Path) -> None:
        try:
            layer = self.iface.addRasterLayer(
                str(output_path), self.tr("几何校正成果")
            )
            if layer is None or not layer.isValid():
                self._append_log(
                    self.tr("[提醒] 成果已生成，但自动加载图层失败。")
                )
                return
            self.iface.mapCanvas().setExtent(layer.extent())
            self.iface.mapCanvas().refresh()
            self._append_log(
                self.tr("[加载] 校正GeoTIFF已加载并缩放到图层。")
            )
        except Exception as exc:
            self._append_log(
                self.tr("[提醒] 自动加载成果失败：{error}").format(
                    error=exc
                )
            )

    def _set_busy(self, busy: bool) -> None:
        self.tabs.setEnabled(not busy)
        self.validate_button.setEnabled(not busy)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(busy)

    def open_output(self) -> None:
        if self._last_run_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_run_dir)))

    def _append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(str(message))

    def closeEvent(self, event) -> None:
        if self._task is not None:
            self.cancel_task()
            event.ignore()
            return
        self._save_preferences()
        super().closeEvent(event)
