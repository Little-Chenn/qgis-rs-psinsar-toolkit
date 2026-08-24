"""QGIS/Qt runtime checks for the compiled English translation catalog."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication


DEV_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = DEV_ROOT / "rs_psinsar_toolkit"
sys.path.insert(0, str(DEV_ROOT))

from rs_psinsar_toolkit.localization import TranslationManager, language_code


class I18nRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_language_normalization(self) -> None:
        self.assertEqual(language_code("en_US"), "en")
        self.assertEqual(language_code("en-GB"), "en")
        self.assertEqual(language_code("zh_CN"), "zh")

    def test_compiled_catalog_loads_and_translates(self) -> None:
        ambient_translation = QCoreApplication.translate("@default", "单位：dB")
        manager = TranslationManager(PLUGIN_DIR)
        manager.language = "en"
        try:
            self.assertTrue(manager.install())
            self.assertTrue(manager.is_loaded)
            self.assertEqual(
                QCoreApplication.translate("@default", "单位：dB"),
                "Unit: dB",
            )
            self.assertEqual(
                QCoreApplication.translate(
                    "SarMapDialog", "SAR 强度 dB 专题制图"
                ),
                "SAR Intensity Mapping in dB",
            )
            translated = QCoreApplication.translate(
                "@default", "PNG 导出失败，QGIS 代码：{code}"
            )
            self.assertIn("{code}", translated)
        finally:
            manager.uninstall()
        self.assertFalse(manager.is_loaded)
        self.assertEqual(
            QCoreApplication.translate("@default", "单位：dB"),
            ambient_translation,
        )


if __name__ == "__main__":
    unittest.main()
