"""Main hub for the integrated release."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from .dialog import ToolkitDialog
from .displacement_batch_dialog import DisplacementBatchDialog
from .geometry_dialog import GeometryCorrectionDialog
from .sar_dialog import SarProcessingDialog
from .sar_map_dialog import SarMapDialog
from .timeseries_dialog import TimeSeriesReviewDialog


class HubDialog(QDialog):
    """Expose only verified modules while showing the integration roadmap."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self._thematic_dialog: ToolkitDialog | None = None
        self._geometry_dialog: GeometryCorrectionDialog | None = None
        self._sar_dialog: SarProcessingDialog | None = None
        self._sar_map_dialog: SarMapDialog | None = None
        self._displacement_batch_dialog: DisplacementBatchDialog | None = None
        self._timeseries_dialog: TimeSeriesReviewDialog | None = None
        self.setObjectName("rs_psinsar_toolkit_hub_dialog")
        self.setWindowTitle(
            self.tr("遥感影像与 PS-InSAR 处理制图工具箱")
        )
        self.resize(900, 620)
        self.setMinimumSize(840, 580)

        title = QLabel(
            self.tr("遥感影像与 PS-InSAR 处理制图工具箱")
        )
        title.setObjectName("hub_title")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 600;")

        subtitle = QLabel(
            self.tr(
                "集成遥感影像预处理、SAR 强度 dB 专题制图与 PS-InSAR 成果分析；"
                "各项任务均创建独立输出目录，保留原始数据和已有成果。"
            )
        )
        subtitle.setObjectName("hub_subtitle")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 11pt;")

        module_grid = QGridLayout()
        module_grid.setHorizontalSpacing(10)
        module_grid.setVerticalSpacing(10)
        module_grid.setColumnStretch(0, 1)
        module_grid.setColumnStretch(1, 1)
        module_grid.setRowStretch(0, 1)
        module_grid.setRowStretch(1, 1)
        module_grid.setRowStretch(2, 1)
        module_grid.addWidget(
            self._module_card(
                self.tr("GCP 几何校正与精度检查"),
                self.tr(
                    "使用外部训练 GCP 对影像进行几何校正，并通过独立检查点"
                    "计算 RMSE，输出校正成果、残差统计及质量检查报告。"
                ),
                self.tr("打开模块"),
                enabled=True,
                callback=self.open_geometry_correction,
            ),
            0,
            0,
        )
        module_grid.addWidget(
            self._module_card(
                self.tr("SAR 影像镶嵌、裁剪与显示增强"),
                self.tr(
                    "识别单景或多景 ORG GeoTIFF，完成覆盖顺序检查、影像镶嵌、"
                    "掩膜裁剪和线性功率转 dB；支持灰度或伪彩色显示、多种拉伸、"
                    "亮度与层次调整及显示产品外缘羽化。"
                ),
                self.tr("打开模块"),
                enabled=True,
                callback=self.open_sar_processing,
            ),
            0,
            1,
        )
        module_grid.addWidget(
            self._module_card(
                self.tr("SAR 强度 dB 专题制图"),
                self.tr(
                    "基于 SAR 强度 dB GeoTIFF 生成可编辑 QGZ 工程、PNG/PDF "
                    "专题图及质量检查报告，并支持填写制图信息。"
                ),
                self.tr("打开模块"),
                enabled=True,
                callback=self.open_sar_map,
            ),
            1,
            0,
        )
        module_grid.addWidget(
            self._module_card(
                self.tr("PS-InSAR 垂直形变速率专题制图"),
                self.tr(
                    "使用已完成质量控制的 PS-InSAR 面状网格数据生成垂直形变速率成果、"
                    "可编辑 QGZ 工程、PNG/PDF 专题图及质量检查报告。"
                ),
                self.tr("打开模块"),
                enabled=True,
                callback=self.open_thematic_map,
            ),
            1,
            1,
        )
        module_grid.addWidget(
            self._module_card(
                self.tr("PS-InSAR 累计形变批量制图"),
                self.tr(
                    "以初始时相为基准逐点计算累计形变量，生成 50 米网格"
                    "中位数成果、多时相 QGZ 工程、PNG/PDF 专题图及质量检查报告。"
                ),
                self.tr("打开模块"),
                enabled=True,
                callback=self.open_displacement_batch,
            ),
            2,
            0,
        )
        module_grid.addWidget(
            self._module_card(
                self.tr("PS-InSAR 多点形变时序回查"),
                self.tr(
                    "按 ps_uid 从多时相 GeoPackage 中只读提取多个点位的形变量序列，"
                    "输出 CSV、点位 GeoPackage、总览图、明细报告及质量检查报告。"
                ),
                self.tr("打开模块"),
                enabled=True,
                callback=self.open_timeseries_review,
            ),
            2,
            1,
        )

        close_button = QPushButton(self.tr("关闭"))
        close_button.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close_button)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addSpacing(8)
        root.addLayout(module_grid, 1)
        root.addLayout(footer)

    def _module_card(
        self,
        title: str,
        description: str,
        button_text: str,
        *,
        enabled: bool,
        callback=None,
    ) -> QGroupBox:
        card = QGroupBox(title)
        card.setMinimumHeight(150)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.setStyleSheet(
            "QGroupBox { font-size: 12pt; font-weight: 600; margin-top: 12px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
            "QLabel { font-size: 10.5pt; font-weight: 400; }"
            "QPushButton { font-size: 10.5pt; font-weight: 400; min-height: 34px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 26, 14, 12)
        layout.setSpacing(8)
        description_label = QLabel(description)
        description_label.setObjectName("module_description")
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        description_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        button = QPushButton(button_text)
        button.setObjectName("module_open_button")
        button.setEnabled(enabled)
        if callback is not None:
            button.clicked.connect(callback)
        layout.addWidget(description_label)
        layout.addStretch(1)
        layout.addWidget(button)
        return card

    def open_thematic_map(self) -> None:
        if self._thematic_dialog is None:
            self._thematic_dialog = ToolkitDialog(
                iface=self.iface,
                parent=self,
                settings_store=getattr(
                    self.iface,
                    "rs_psinsar_settings_store",
                    None,
                ),
            )
            self._thematic_dialog.setWindowTitle(
                self.tr("PS-InSAR 垂直形变速率专题制图")
            )
        self._thematic_dialog.show()
        self._thematic_dialog.raise_()
        self._thematic_dialog.activateWindow()

    def open_geometry_correction(self) -> None:
        if self._geometry_dialog is None:
            self._geometry_dialog = GeometryCorrectionDialog(
                iface=self.iface,
                parent=self,
                settings_store=getattr(
                    self.iface,
                    "rs_psinsar_settings_store",
                    None,
                ),
            )
        self._geometry_dialog.show()
        self._geometry_dialog.raise_()
        self._geometry_dialog.activateWindow()

    def open_sar_processing(self) -> None:
        if self._sar_dialog is None:
            self._sar_dialog = SarProcessingDialog(
                iface=self.iface,
                parent=self,
                settings_store=getattr(
                    self.iface,
                    "rs_psinsar_settings_store",
                    None,
                ),
            )
        self._sar_dialog.show()
        self._sar_dialog.raise_()
        self._sar_dialog.activateWindow()

    def open_sar_map(self) -> None:
        if self._sar_map_dialog is None:
            self._sar_map_dialog = SarMapDialog(
                iface=self.iface,
                parent=self,
                settings_store=getattr(
                    self.iface,
                    "rs_psinsar_settings_store",
                    None,
                ),
            )
        self._sar_map_dialog.show()
        self._sar_map_dialog.raise_()
        self._sar_map_dialog.activateWindow()

    def open_displacement_batch(self) -> None:
        if self._displacement_batch_dialog is None:
            self._displacement_batch_dialog = DisplacementBatchDialog(
                iface=self.iface,
                parent=self,
                settings_store=getattr(
                    self.iface,
                    "rs_psinsar_settings_store",
                    None,
                ),
            )
        self._displacement_batch_dialog.show()
        self._displacement_batch_dialog.raise_()
        self._displacement_batch_dialog.activateWindow()

    def open_timeseries_review(self) -> None:
        if self._timeseries_dialog is None:
            self._timeseries_dialog = TimeSeriesReviewDialog(
                iface=self.iface,
                parent=self,
                settings_store=getattr(
                    self.iface,
                    "rs_psinsar_settings_store",
                    None,
                ),
            )
        self._timeseries_dialog.show()
        self._timeseries_dialog.raise_()
        self._timeseries_dialog.activateWindow()

    def closeEvent(self, event) -> None:
        if self._timeseries_dialog is not None:
            self._timeseries_dialog.close()
            if self._timeseries_dialog.isVisible():
                event.ignore()
                return
        if self._displacement_batch_dialog is not None:
            self._displacement_batch_dialog.close()
            if self._displacement_batch_dialog.isVisible():
                event.ignore()
                return
        if self._sar_map_dialog is not None:
            self._sar_map_dialog.close()
            if self._sar_map_dialog.isVisible():
                event.ignore()
                return
        if self._sar_dialog is not None:
            self._sar_dialog.close()
            if self._sar_dialog.isVisible():
                event.ignore()
                return
        if self._geometry_dialog is not None:
            self._geometry_dialog.close()
            if self._geometry_dialog.isVisible():
                event.ignore()
                return
        if self._thematic_dialog is not None:
            self._thematic_dialog.close()
        super().closeEvent(event)
