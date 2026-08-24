"""QGIS lifecycle integration for the RS & PS-InSAR toolkit."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import Qgis, QgsMessageLog

from .hub_dialog import HubDialog
from .localization import TranslationManager


LOG_TAG = "RS PS-InSAR Toolkit"


class RsPsInsarToolkitPlugin:
    """Own the QGIS menu action and the modeless plugin dialog."""

    def __init__(self, iface):
        self.iface = iface
        self.action: QAction | None = None
        self.dialog: HubDialog | None = None
        self.plugin_dir = Path(__file__).resolve().parent
        self.translation_manager = TranslationManager(self.plugin_dir)
        self.translation_manager.install()
        self.menu_text = QCoreApplication.translate(
            "RsPsInsarToolkitPlugin",
            "&遥感影像与 PS-InSAR 处理制图工具箱",
        )

    def initGui(self) -> None:
        icon = QIcon(str(self.plugin_dir / "icon.svg"))
        self.action = QAction(
            icon,
            QCoreApplication.translate(
                "RsPsInsarToolkitPlugin", "打开工具箱"
            ),
            self.iface.mainWindow(),
        )
        self.action.setObjectName("rs_psinsar_toolkit_action")
        self.action.setToolTip(
            QCoreApplication.translate(
                "RsPsInsarToolkitPlugin",
                "打开“遥感影像与 PS-InSAR 处理制图工具箱”",
            )
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu(self.menu_text, self.action)
        self.iface.addToolBarIcon(self.action)
        QgsMessageLog.logMessage(
            QCoreApplication.translate(
                "RsPsInsarToolkitPlugin",
                "遥感影像与 PS-InSAR 处理制图工具箱已加载",
            ),
            LOG_TAG,
            Qgis.Info,
        )

    def unload(self) -> None:
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        if self.action is not None:
            self.iface.removePluginMenu(self.menu_text, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
        QgsMessageLog.logMessage(
            QCoreApplication.translate(
                "RsPsInsarToolkitPlugin",
                "遥感影像与 PS-InSAR 处理制图工具箱已卸载",
            ),
            LOG_TAG,
            Qgis.Info,
        )
        self.translation_manager.uninstall()

    def run(self) -> None:
        if self.dialog is None:
            self.dialog = HubDialog(
                iface=self.iface,
                parent=self.iface.mainWindow(),
            )
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
