"""Acceptance gates for bilingual map and time-series review modules."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication


DEV_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = DEV_ROOT / "rs_psinsar_toolkit"
TS_PATH = PLUGIN_DIR / "i18n" / "rs_psinsar_toolkit_en.ts"
TEMPLATE_DIR = PLUGIN_DIR / "templates"
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class Modules456I18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])
        cls.catalog = catalog_messages()

    def test_expected_context_coverage_and_catalog_completion(self) -> None:
        counts: dict[str, int] = {}
        for context, _source in self.catalog:
            counts[context] = counts.get(context, 0) + 1
        self.assertGreaterEqual(counts.get("ToolkitDialog", 0), 68)
        self.assertGreaterEqual(counts.get("DisplacementBatchDialog", 0), 71)
        self.assertGreaterEqual(counts.get("TimeSeriesReviewDialog", 0), 56)
        root = ET.parse(TS_PATH).getroot()
        unfinished = [
            message
            for message in root.findall(".//message")
            if message.find("translation") is None
            or message.find("translation").get("type") == "unfinished"
        ]
        self.assertEqual(unfinished, [])

    def test_scientific_boundaries_are_explicit_in_english(self) -> None:
        rate = self.catalog[
            (
                "ToolkitDialog",
                "输入要求：所选图层应为具有有效坐标参考系的面状网格图层，"
                "数值字段应表示垂直形变速率，单位为 mm/年。正值表示垂直向上，"
                "负值表示垂直向下。本模块不重新计算形变速率，也不自动判定异常值及其物理原因。",
            )
        ]
        self.assertIn("mm/year", rate)
        self.assertIn("Positive values indicate upward motion", rate)
        self.assertIn("does not recompute", rate)
        self.assertIn("vertical displacement rate", rate)

        cumulative = self.catalog[
            (
                "DisplacementBatchDialog",
                "计算方法与结果说明：先对每个 PS 点计算目标时相与初始时相之差 "
                "ΔDₜ = Dₜ − D₀，再统计每个 50 m 网格内有效点差值的中位数。"
                "结果单位为 mm；正值表示垂直向上，负值表示垂直向下。"
                "专题图统一采用 −20 mm 和 20 mm 作为外侧分级界限，不叠加原始极端点。",
            )
        ]
        self.assertIn("ΔDₜ = Dₜ − D₀", cumulative)
        self.assertIn("50 m grid", cumulative)
        self.assertIn("median", cumulative)
        self.assertIn("Results are in mm", cumulative)

        review = self.catalog[
            (
                "TimeSeriesReviewDialog",
                "结果用于人工回查和对比分析。形变量单位为 mm，正值表示垂直向上，"
                "负值表示垂直向下；本模块不自动判定异常点、趋势类型或物理原因，"
                "也不重新计算形变结果。",
            )
        ]
        self.assertIn("manual review", review)
        self.assertIn("does not automatically identify", review)
        self.assertNotRegex(review, re.compile(r"automatic anomaly identification", re.I))

    def test_machine_contracts_remain_stable(self) -> None:
        rate = (PLUGIN_DIR / "builder.py").read_text(encoding="utf-8")
        cumulative = (PLUGIN_DIR / "displacement_batch_core.py").read_text(
            encoding="utf-8"
        )
        cumulative_settings = (
            PLUGIN_DIR / "displacement_batch_settings.py"
        ).read_text(encoding="utf-8")
        review = (PLUGIN_DIR / "timeseries_core.py").read_text(encoding="utf-8")
        review_settings = (PLUGIN_DIR / "timeseries_settings.py").read_text(
            encoding="utf-8"
        )
        for value in (
            '"rs_psinsar/velocity_unit", "mm/year"',
            '"rs_psinsar/positive_direction", "vertical upward"',
            '"rs_psinsar/negative_direction", "vertical downward"',
            'status = "PASS" if all(checks.values()) else "REVIEW"',
        ):
            self.assertIn(value, rate)
        for value in (
            '"formula", "D_target - D_initial"',
            '"formula": "delta_mm = D_target - D_initial"',
            'batch_delta = target_values - initial_values[:, None]',
            '"positive_direction": "vertical upward"',
            '"negative_direction": "vertical downward"',
        ):
            self.assertIn(value, cumulative)
        self.assertIn("DEFAULT_GRID_SIZE_M = 50.0", cumulative_settings)
        self.assertIn("DEFAULT_DISPLAY_BOUND_MM = 20.0", cumulative_settings)
        self.assertIn("DEFAULT_DISPLAY_BOUND_M = DEFAULT_DISPLAY_BOUND_MM", cumulative_settings)
        self.assertIn(
            'status = "PASS" if all(acceptance_checks.values()) else "REVIEW"',
            review,
        )
        self.assertIn('if key != "unit_is_m"', review)
        self.assertIn(
            '"descriptive review only; no automatic anomaly or physical-cause classification"',
            review,
        )
        for directory in (
            'run_dir / "01_数据表"',
            'run_dir / "02_点位图层"',
            'run_dir / "03_图表"',
            'run_dir / "04_质量报告"',
        ):
            self.assertIn(directory, review)
        for mode in (
            'mode = "点位清单原样回查"',
            'mode = "A/B×LOW/HIGH 受控抽样"',
            'mode = "ps_uid 清单原样回查"',
        ):
            self.assertIn(mode, review_settings)

    def test_english_qpt_derivatives_have_verified_provenance(self) -> None:
        pairs = (
            ("plugin_overview_template_v5", "m341_title"),
            ("cumulative_displacement_template_v1", "title"),
        )
        for stem, required_id in pairs:
            source = TEMPLATE_DIR / f"{stem}.qpt"
            output = TEMPLATE_DIR / f"{stem}_en.qpt"
            report = json.loads(
                (TEMPLATE_DIR / f"{stem}_en_report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["derived_from_sha256"], sha256(source))
            self.assertEqual(report["output_qpt_sha256"], sha256(output))
            if stem == "plugin_overview_template_v5":
                self.assertEqual(report["output_sha256"], sha256(output))
            output_text = output.read_text(encoding="utf-8")
            self.assertNotRegex(output_text, r"[\u3400-\u9fff]")
            source_ids = set(re.findall(r'\bid="([^"]+)"', source.read_text(encoding="utf-8")))
            output_ids = set(re.findall(r'\bid="([^"]+)"', output_text))
            self.assertEqual(source_ids, output_ids)
            if required_id != "title":
                self.assertIn(required_id, output_ids)
            self.assertNotRegex(
                output_text,
                r'fontFamily="(?!Times New Roman)[^"]+"|<family name="(?!Times New Roman)[^"]+"',
            )
        cumulative_qpt = (
            TEMPLATE_DIR / "cumulative_displacement_template_v1_en.qpt"
        ).read_text(encoding="utf-8")
        self.assertIn("Unit: mm", cumulative_qpt)
        self.assertNotIn("Unit: m&#xa;", cumulative_qpt)

    def test_compiled_catalog_translates_modules456_at_runtime(self) -> None:
        manager = TranslationManager(PLUGIN_DIR)
        manager.language = "en"
        try:
            self.assertTrue(manager.install())
            self.assertEqual(
                QCoreApplication.translate(
                    "ToolkitDialog", "PS-InSAR 垂直形变速率专题制图"
                ),
                "PS-InSAR Vertical Displacement Rate Mapping",
            )
            self.assertEqual(
                QCoreApplication.translate(
                    "DisplacementBatchDialog", "开始批量制图"
                ),
                "Start Batch Mapping",
            )
            self.assertEqual(
                QCoreApplication.translate(
                    "TimeSeriesReviewDialog", "PS-InSAR 多点形变时序回查"
                ),
                "PS-InSAR Multi-point Displacement Time-series Review",
            )
            self.assertEqual(
                QCoreApplication.translate("@default", "组内中位数"),
                "Group Median",
            )
        finally:
            manager.uninstall()


if __name__ == "__main__":
    unittest.main()
