"""QGIS dialog for the independent multi-point time-series review module."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QSettings, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox,
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer

from .timeseries_core import (
    TimeSeriesCancelled,
    TimeSeriesRunError,
    run_timeseries_review,
)
from .timeseries_settings import (
    TimeSeriesSettings,
    inspect_inputs,
    localized_point_mode,
    validate_settings,
)


class TimeSeriesReviewDialog(QDialog):
    """Collect and run one safe, non-overwriting time-series review job."""

    def __init__(self, iface, parent=None, settings_store=None):
        super().__init__(parent)
        self.iface = iface
        self._settings = (
            settings_store
            if settings_store is not None
            else QSettings("PyQGISProject", "rs_psinsar_toolkit")
        )
        self._running = False
        self._cancel_requested = False
        self._last_run_dir: Path | None = None
        self.setObjectName("timeseries_review_dialog")
        self.setWindowTitle(self.tr("PS-InSAR 多点形变时序回查"))
        self.resize(880, 690)

        intro = QLabel(
            self.tr(
                "本模块从多时相 GeoPackage 中按 ps_uid 提取多个 PS 点的完整形变量序列，"
                "输出时序长表、统计摘要、点位 GeoPackage、总览图、明细报告和质量检查报告。"
                "所有输入均以只读方式使用。"
            )
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            "background:#eaf3ff; border:1px solid #6a9fd4; padding:8px;"
        )
        notice = QLabel(
            self.tr(
                "结果用于人工回查和对比分析。形变量单位为 mm，正值表示垂直向上，"
                "负值表示垂直向下；本模块不自动判定异常点、趋势类型或物理原因，"
                "也不重新计算形变结果。"
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "background:#FFF7D6; border:1px solid #E4C95B; padding:8px;"
        )

        input_group = QGroupBox(self.tr("输入数据"))
        input_form = QFormLayout(input_group)
        row, self.gpkg_edit, self.gpkg_button = self._path_row(
            self.tr("选择包含时相目录和PS点位的多时相 GeoPackage")
        )
        input_form.addRow(self.tr("多时相 GeoPackage："), row)
        row, self.csv_edit, self.csv_button = self._path_row(
            self.tr("选择含 ps_uid 的点位清单或完整候选表 CSV")
        )
        input_form.addRow(self.tr("点位清单（CSV）："), row)
        row, self.output_edit, self.output_button = self._path_row(
            self.tr("选择输出根目录；任务将自动创建时间戳子目录")
        )
        input_form.addRow(self.tr("输出根目录："), row)

        selection_group = QGroupBox(self.tr("点位规则"))
        selection_form = QFormLayout(selection_group)
        note = QLabel(
            self.tr(
                "点位选择规则：含 selection_rank 的清单按既定顺序回查；"
                "仅含 ps_uid 的清单按文件顺序回查；完整候选表按候选类型和方向分层抽样。"
            )
        )
        note.setWordWrap(True)
        selection_form.addRow(self.tr("识别规则："), note)
        self.quota_spin = QSpinBox()
        self.quota_spin.setRange(1, 50)
        self.quota_spin.setValue(12)
        self.quota_spin.setSuffix(self.tr(" 点/层"))
        selection_form.addRow(self.tr("每层抽样点数："), self.quota_spin)
        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(0.0, 100_000.0)
        self.distance_spin.setDecimals(1)
        self.distance_spin.setValue(500.0)
        self.distance_spin.setSuffix(" m")
        selection_form.addRow(self.tr("点位最小间距："), self.distance_spin)
        self.quota_spin.setEnabled(False)
        self.distance_spin.setEnabled(False)
        sampling_note = QLabel(
            self.tr(
                "完整候选表默认分为聚集型（A）/孤立型（B）和低值侧（LOW）/"
                "高值侧（HIGH）四层；每层抽取相同数量，并执行全局最小间距约束。"
                "C 类保留在候选表中，但不进入默认抽样。上述分层仅用于组织回查样本，"
                "不代表物理成因分类。"
            )
        )
        sampling_note.setWordWrap(True)
        sampling_note.setStyleSheet("color:#555555;")
        selection_form.addRow(self.tr("抽样说明："), sampling_note)
        inspect_row = QHBoxLayout()
        self.inspect_button = QPushButton(self.tr("只读检查输入"))
        self.inspection_label = QLabel(self.tr("尚未检查"))
        self.inspection_label.setWordWrap(True)
        inspect_row.addWidget(self.inspect_button)
        inspect_row.addWidget(self.inspection_label, 1)
        selection_form.addRow(self.tr("输入摘要："), inspect_row)

        output_group = QGroupBox(self.tr("输出成果"))
        output_form = QFormLayout(output_group)
        format_row = QHBoxLayout()
        self.export_csv = QCheckBox(self.tr("长表与摘要 CSV"))
        self.export_gpkg = QCheckBox(self.tr("点位 GeoPackage"))
        self.export_png = QCheckBox(self.tr("总览 PNG"))
        self.export_pdf = QCheckBox(self.tr("明细 PDF"))
        for checkbox in (
            self.export_csv,
            self.export_gpkg,
            self.export_png,
            self.export_pdf,
        ):
            checkbox.setChecked(True)
            format_row.addWidget(checkbox)
        format_row.addStretch(1)
        output_form.addRow(self.tr("成果："), format_row)
        self.load_result = QCheckBox(
            self.tr("完成后加载点位结果并缩放至图层范围")
        )
        self.load_result.setChecked(True)
        output_form.addRow(self.tr("QGIS："), self.load_result)

        status_group = QGroupBox(self.tr("执行与日志"))
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel(self.tr("请检查输入数据"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        actions = QHBoxLayout()
        self.validate_button = QPushButton(self.tr("检查当前设置"))
        self.run_button = QPushButton(self.tr("开始多点形变时序回查"))
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
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress)
        status_layout.addWidget(self.log, 1)
        status_layout.addLayout(actions)

        close_button = QPushButton(self.tr("关闭"))
        close_button.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close_button)

        root = QVBoxLayout(self)
        root.addWidget(intro)
        root.addWidget(notice)
        root.addWidget(input_group)
        root.addWidget(selection_group)
        root.addWidget(output_group)
        root.addWidget(status_group, 1)
        root.addLayout(footer)

        self._connect()
        self._load_preferences()
        self._append_log(
            self.tr(
                "PS-InSAR 多点形变时序回查模块已就绪。请选择多时相 GeoPackage、"
                "点位清单和输出目录，然后检查输入数据。"
            )
        )

    def _path_row(self, placeholder: str) -> tuple[QWidget, QLineEdit, QPushButton]:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        button = QPushButton(self.tr("浏览…"))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return container, edit, button

    def _connect(self) -> None:
        self.gpkg_button.clicked.connect(self._browse_gpkg)
        self.csv_button.clicked.connect(self._browse_csv)
        self.output_button.clicked.connect(self._browse_output)
        self.inspect_button.clicked.connect(self.inspect_current)
        self.validate_button.clicked.connect(self.validate_current)
        self.run_button.clicked.connect(self.run_review)
        self.cancel_button.clicked.connect(self.request_cancel)
        self.open_button.clicked.connect(self.open_output)
        self.gpkg_edit.textChanged.connect(self._input_changed)
        self.csv_edit.textChanged.connect(self._input_changed)

    def _input_changed(self) -> None:
        if self._running:
            return
        self.run_button.setEnabled(False)
        self.quota_spin.setEnabled(False)
        self.distance_spin.setEnabled(False)
        self.inspection_label.setText(self.tr("尚未检查"))
        self.status_label.setText(self.tr("输入已更改，请重新检查"))

    def _load_preferences(self) -> None:
        prefix = "m90/"
        self.gpkg_edit.setText(str(self._settings.value(prefix + "input_gpkg", "")))
        self.csv_edit.setText(str(self._settings.value(prefix + "point_csv", "")))
        self.output_edit.setText(str(self._settings.value(prefix + "output_root", "")))

    def _save_preferences(self) -> None:
        prefix = "m90/"
        self._settings.setValue(prefix + "input_gpkg", self.gpkg_edit.text())
        self._settings.setValue(prefix + "point_csv", self.csv_edit.text())
        self._settings.setValue(prefix + "output_root", self.output_edit.text())
        self._settings.sync()

    def current_settings(self) -> TimeSeriesSettings:
        return TimeSeriesSettings(
            input_gpkg=self.gpkg_edit.text().strip(),
            point_csv=self.csv_edit.text().strip(),
            output_root=self.output_edit.text().strip(),
            quota_per_stratum=self.quota_spin.value(),
            minimum_distance_m=self.distance_spin.value(),
            export_csv=self.export_csv.isChecked(),
            export_gpkg=self.export_gpkg.isChecked(),
            export_png=self.export_png.isChecked(),
            export_pdf=self.export_pdf.isChecked(),
            load_result=self.load_result.isChecked(),
        )

    def inspect_current(self) -> None:
        try:
            inspection = inspect_inputs(self.current_settings())
            initial = next(item for item in inspection.fields if item.is_initial)
            last = inspection.fields[-1]
            self.inspection_label.setText(
                self.tr(
                    "{mode}；输入 {row_count:,} 行，将回查 {point_count} 点；"
                    "{date_count} 期（{first_date}—{last_date}）；单位 mm"
                ).format(
                    mode=localized_point_mode(inspection.point_mode),
                    row_count=inspection.source_row_count,
                    point_count=inspection.selected_point_count,
                    date_count=len(inspection.fields),
                    first_date=initial.acquisition_date,
                    last_date=last.acquisition_date,
                )
            )
            sampled = "受控抽样" in inspection.point_mode
            self.quota_spin.setEnabled(sampled)
            self.distance_spin.setEnabled(sampled)
            self._append_log(
                self.tr("[PASS] 输入数据与时相目录只读检查通过。")
            )
        except Exception as exc:
            self.inspection_label.setText(self.tr("检查失败"))
            self.quota_spin.setEnabled(False)
            self.distance_spin.setEnabled(False)
            self._append_log(f"[FAILED] {exc}")

    def validate_current(self) -> list[str]:
        settings = self.current_settings()
        errors = validate_settings(settings)
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
            inspection = inspect_inputs(settings)
            self.status_label.setText(
                self.tr("设置通过：将回查 {point_count} 点、{date_count} 期").format(
                    point_count=inspection.selected_point_count,
                    date_count=len(inspection.fields),
                )
            )
            self.run_button.setEnabled(True)
            self._save_preferences()
            self.inspect_current()
        return errors

    def run_review(self) -> None:
        if self.validate_current():
            return
        self._running = True
        self._cancel_requested = False
        self._last_run_dir = None
        self.progress.setValue(0)
        self._set_busy(True)
        try:
            result = run_timeseries_review(
                self.current_settings(),
                progress=self._on_progress,
                is_cancelled=lambda: self._cancel_requested,
            )
            self._last_run_dir = result.run_dir
            self.open_button.setEnabled(True)
            if self.load_result.isChecked() and "point_gpkg" in result.artifacts:
                self._load_point_layer(Path(result.artifacts["point_gpkg"]))
            self.status_label.setText(
                self.tr("完成：{point_count} 点 × {date_count} 期").format(
                    point_count=result.point_count,
                    date_count=result.date_count,
                )
            )
            self._append_log(
                self.tr("[PASS] 输出目录：{path}").format(
                    path=result.run_dir
                )
            )
        except TimeSeriesCancelled as exc:
            self.status_label.setText(self.tr("任务已取消；输入未被修改"))
            self._append_log(f"[CANCELLED] {exc}")
        except (TimeSeriesRunError, OSError, RuntimeError, ValueError) as exc:
            self.status_label.setText(
                self.tr("任务失败；请检查任务目录内的诊断报告")
            )
            self._append_log(f"[FAILED] {exc}")
        finally:
            self._running = False
            self._set_busy(False)

    def request_cancel(self) -> None:
        self._cancel_requested = True
        self.cancel_button.setEnabled(False)
        self.status_label.setText(
            self.tr("已请求取消；将在下一安全检查点停止")
        )
        self._append_log(self.tr("[取消] 已收到取消请求。"))

    def _load_point_layer(self, path: Path) -> None:
        uri = f"{path}|layername=selected_timeseries_points"
        layer = QgsVectorLayer(
            uri, self.tr("多点形变时序回查点位"), "ogr"
        )
        if not layer.isValid():
            self._append_log(
                self.tr("[提醒] 点位 GeoPackage 已生成，但未能自动加载。")
            )
            return
        QgsProject.instance().addMapLayer(layer)
        self.iface.setActiveLayer(layer)
        self.iface.mapCanvas().setExtent(layer.extent())
        self.iface.mapCanvas().refresh()

    def _on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.status_label.setText(message)
        self._append_log(f"[{value}%] {message}")
        QgsApplication.processEvents()

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.inspect_button,
            self.validate_button,
            self.run_button,
            self.gpkg_button,
            self.csv_button,
            self.output_button,
        ):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def open_output(self) -> None:
        if self._last_run_dir and self._last_run_dir.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_run_dir)))

    def _browse_gpkg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择多时相 GeoPackage"), "", "GeoPackage (*.gpkg)"
        )
        if path:
            self.gpkg_edit.setText(path)

    def _browse_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("选择点位 CSV"), "", "CSV (*.csv)"
        )
        if path:
            self.csv_edit.setText(path)

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
