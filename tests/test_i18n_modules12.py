"""Acceptance gates for bilingual geometry and SAR-processing modules."""

from __future__ import annotations

import ast
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication


DEV_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = DEV_ROOT / "rs_psinsar_toolkit"
TS_PATH = PLUGIN_DIR / "i18n" / "rs_psinsar_toolkit_en.ts"
sys.path.insert(0, str(DEV_ROOT))

from rs_psinsar_toolkit.localization import TranslationManager


def catalog_messages() -> dict[tuple[str, str], str]:
    values: dict[tuple[str, str], str] = {}
    root = ET.parse(TS_PATH).getroot()
    for context in root.findall("context"):
        name = context.findtext("name") or ""
        for message in context.findall("message"):
            source = message.findtext("source") or ""
            translation = message.findtext("translation") or ""
            values[(name, source)] = translation
    return values


class Modules12I18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])
        cls.catalog = catalog_messages()

    def test_expected_context_coverage(self) -> None:
        counts: dict[str, int] = {}
        for context, _source in self.catalog:
            counts[context] = counts.get(context, 0) + 1
        self.assertGreaterEqual(counts.get("GeometryCorrectionDialog", 0), 90)
        self.assertGreaterEqual(counts.get("SarProcessingDialog", 0), 121)
        self.assertGreaterEqual(counts.get("@default", 0), 300)

    def test_scientific_boundaries_are_explicit_in_english(self) -> None:
        calibration_source = (
            "未发现完整Sigma0/Gamma0等辐射定标信息；"
            "输出语义限定为“强度dB”。"
        )
        calibration = self.catalog[("@default", calibration_source)]
        self.assertIn("intensity in dB", calibration)
        self.assertIn("was not found", calibration)
        self.assertNotRegex(calibration, r"(?i)output is (sigma0|gamma0)")

        scope_source = (
            "适用范围：本模式基于外部 GCP 执行影像到地图坐标的几何校正，"
            "支持一阶仿射、二阶/三阶多项式和薄板样条（TPS），并使用独立检查点评估 RMSE。"
            "本模式不使用 SAR 轨道、传感器模型或 DEM，不属于 Range-Doppler 地形校正。"
        )
        scope = self.catalog[("GeometryCorrectionDialog", scope_source)]
        self.assertIn("image-to-map", scope)
        self.assertIn("is not Range-Doppler terrain correction", scope)

    def test_machine_contract_strings_remain_stable(self) -> None:
        geometry = (PLUGIN_DIR / "geometry_real_workflow.py").read_text(
            encoding="utf-8"
        )
        sar = (PLUGIN_DIR / "sar_workflow.py").read_text(encoding="utf-8")
        for value in (
            '"real_external_gcp_image_to_map"',
            '"PASS"',
            '"FAIL_ACCURACY_THRESHOLD"',
            '"COMPLETED_REQUIRES_HUMAN_ACCURACY_REVIEW"',
            '"geometry_correction_report.json"',
            '"train_residuals.csv"',
            '"check_residuals.csv"',
        ):
            self.assertIn(value, geometry)
        for value in (
            'RUN_INFO_DIR = "00_运行记录"',
            'MOSAIC_DIR = "01_线性镶嵌"',
            'CLIP_DIR = "02_线性裁剪"',
            'DB_DIR = "03_dB成果"',
            'QUALITY_DIR = "04_质量报告"',
            'DISPLAY_DIR = "05_显示产品"',
            "10*log10(linear_power)",
            '"sar_mosaic_clip_db.tif"',
        ):
            self.assertIn(value, sar)

    def test_compiled_catalog_translates_modules12_at_runtime(self) -> None:
        manager = TranslationManager(PLUGIN_DIR)
        manager.language = "en"
        try:
            self.assertTrue(manager.install())
            self.assertEqual(
                QCoreApplication.translate(
                    "GeometryCorrectionDialog", "GCP 几何校正与精度检查"
                ),
                "GCP Geometric Correction and Accuracy Assessment",
            )
            self.assertEqual(
                QCoreApplication.translate(
                    "SarProcessingDialog", "组间中位强度异常"
                ),
                "between-group median-intensity anomaly",
            )
            progress = QCoreApplication.translate(
                "@default", "步骤3/4：线性功率转dB。"
            )
            self.assertEqual(progress, "Step 3/4: Convert linear power to dB.")
            report_heading = QCoreApplication.translate(
                "@default", "# 几何校正与独立精度检查报告\n\n"
            )
            self.assertEqual(
                report_heading,
                "# Geometric Correction and Independent Accuracy Assessment Report\n\n",
            )
        finally:
            manager.uninstall()

    def test_no_overclaim_in_module12_english_catalog(self) -> None:
        english = "\n".join(
            value
            for (context, _source), value in self.catalog.items()
            if context in {"GeometryCorrectionDialog", "SarProcessingDialog", "@default"}
        )
        self.assertNotRegex(english, re.compile(r"automatic anomaly (detection|identification)", re.I))
        self.assertNotRegex(english, re.compile(r"performs Range-Doppler", re.I))

    def test_static_dialog_helpers_do_not_reference_self(self) -> None:
        """Prevent the module-2 GUI regression found by real QGIS startup."""
        tree = ast.parse((PLUGIN_DIR / "sar_dialog.py").read_text(encoding="utf-8"))
        violations: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = {
                item.id for item in node.decorator_list if isinstance(item, ast.Name)
            }
            if "staticmethod" not in decorators:
                continue
            if any(
                isinstance(item, ast.Name) and item.id == "self"
                for item in ast.walk(node)
            ):
                violations.append(f"{node.name}:{node.lineno}")
        self.assertEqual(violations, [])

    def test_modules12_use_resizable_compact_layouts(self) -> None:
        geometry = (PLUGIN_DIR / "geometry_dialog.py").read_text(encoding="utf-8")
        sar = (PLUGIN_DIR / "sar_dialog.py").read_text(encoding="utf-8")
        self.assertIn('self.setMinimumSize(720, 560)', geometry)
        self.assertIn('self.setSizeGripEnabled(True)', geometry)
        self.assertIn('QScrollArea', geometry)
        self.assertNotIn('setFixedSize(', geometry)
        self.assertIn('self.setMinimumSize(720, 560)', sar)
        self.assertIn('self.setSizeGripEnabled(True)', sar)
        self.assertIn('section_tabs.setObjectName("sar_section_tabs")', sar)
        self.assertIn('self.tr("输入与顺序")', sar)
        self.assertIn('self.tr("处理与显示")', sar)
        self.assertIn('self.tr("科学确认")', sar)
        self.assertNotIn('setFixedSize(', sar)

    def test_new_sar_section_tabs_translate_at_runtime(self) -> None:
        manager = TranslationManager(PLUGIN_DIR)
        manager.language = "en"
        try:
            self.assertTrue(manager.install())
            for source, expected in (
                ("输入与顺序", "Inputs and Order"),
                ("处理与显示", "Processing and Display"),
                ("科学确认", "Scientific Confirmations"),
            ):
                self.assertEqual(
                    QCoreApplication.translate("SarProcessingDialog", source),
                    expected,
                )
        finally:
            manager.uninstall()

    def test_translated_report_builder_has_no_unary_plus_on_text(self) -> None:
        """Prevent the module-3 report regression found by real QGIS export."""
        tree = ast.parse(
            (PLUGIN_DIR / "sar_map_builder.py").read_text(encoding="utf-8")
        )
        lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.UAdd)
            and isinstance(node.operand, ast.Call)
            and isinstance(node.operand.func, ast.Name)
            and node.operand.func.id == "_tr"
        ]
        self.assertEqual(lines, [])


if __name__ == "__main__":
    unittest.main()
