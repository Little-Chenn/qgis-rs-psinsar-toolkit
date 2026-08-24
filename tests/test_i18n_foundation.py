"""Static acceptance gates for the bilingual 0.3.0-rc1 candidate."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1] / "rs_psinsar_toolkit"
TS_PATH = PLUGIN_DIR / "i18n" / "rs_psinsar_toolkit_en.ts"
EN_QPT_PATH = PLUGIN_DIR / "templates" / "backscatter_template_v1_en.qpt"
EN_QPT_REPORT_PATH = (
    PLUGIN_DIR / "templates" / "backscatter_template_v1_en_report.json"
)
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}|%\d+|%n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class I18nFoundationTests(unittest.TestCase):
    def test_version_and_metadata_are_rc1(self) -> None:
        version_text = (PLUGIN_DIR / "version.py").read_text(encoding="utf-8")
        metadata_text = (PLUGIN_DIR / "metadata.txt").read_text(encoding="utf-8")
        self.assertIn('PLUGIN_VERSION = "0.3.0-rc1"', version_text)
        self.assertIn("version=0.3.0-rc1", metadata_text)
        self.assertIn("SAR intensity processing and mapping in dB", metadata_text)
        self.assertNotIn("Sigma0", metadata_text)
        self.assertNotIn("Gamma0", metadata_text)
        self.assertNotIn("Range-Doppler", metadata_text)

    def test_english_catalog_is_complete_and_preserves_placeholders(self) -> None:
        root = ET.parse(TS_PATH).getroot()
        self.assertEqual(root.attrib.get("language"), "en")
        self.assertEqual(root.attrib.get("sourcelanguage"), "zh_CN")
        messages = root.findall("./context/message")
        self.assertGreaterEqual(len(messages), 150)
        for message in messages:
            source = message.findtext("source") or ""
            translation = message.find("translation")
            self.assertIsNotNone(translation, source)
            self.assertNotIn(
                translation.attrib.get("type", ""),
                {"unfinished", "obsolete", "vanished"},
                source,
            )
            translated_text = "".join(translation.itertext())
            self.assertTrue(translated_text.strip(), source)
            self.assertEqual(
                sorted(PLACEHOLDER_RE.findall(source)),
                sorted(PLACEHOLDER_RE.findall(translated_text)),
                source,
            )

    def test_english_qpt_is_text_only_derivative_with_valid_provenance(self) -> None:
        report = json.loads(EN_QPT_REPORT_PATH.read_text(encoding="utf-8"))
        qpt_text = EN_QPT_PATH.read_text(encoding="utf-8")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["language"], "en")
        self.assertEqual(report["output_qpt_sha256"], sha256(EN_QPT_PATH))
        self.assertFalse(HAN_RE.search(qpt_text))
        self.assertIn("SAR Intensity Map in dB", qpt_text)
        self.assertIn("VV-polarized SAR Intensity", qpt_text)
        self.assertNotIn("Sigma0", qpt_text)
        self.assertNotIn("Gamma0", qpt_text)
        for item_id in report["required_item_ids"]:
            self.assertRegex(qpt_text, rf'\bid="{re.escape(item_id)}"')

    def test_migrated_module3_uses_scientifically_bounded_wording(self) -> None:
        paths = [
            PLUGIN_DIR / "metadata.txt",
            PLUGIN_DIR / "hub_dialog.py",
            PLUGIN_DIR / "sar_map_dialog.py",
            PLUGIN_DIR / "sar_map_settings.py",
            PLUGIN_DIR / "sar_map_builder.py",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotIn("后向散射", combined)
        self.assertIn("SAR 强度", combined)
        self.assertIn("缺少完整 Sigma0/Gamma0 定标证据", combined)
        self.assertIn("仅表述为 SAR 强度 dB", combined)

    def test_runtime_template_switch_does_not_change_internal_filenames(self) -> None:
        builder_text = (PLUGIN_DIR / "sar_map_builder.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('TEMPLATE_NAME_ZH = "backscatter_template_v1.qpt"', builder_text)
        self.assertIn('TEMPLATE_NAME_EN = "backscatter_template_v1_en.qpt"', builder_text)
        self.assertIn('"sar_backscatter_db.tif"', builder_text)
        self.assertIn('"sar_backscatter_map.qgz"', builder_text)
        self.assertIn('"PASS"', builder_text)
        tasking_text = (PLUGIN_DIR / "tasking.py").read_text(encoding="utf-8")
        for status in ("CREATED", "RUNNING", "PASS", "FAILED", "CANCELLED"):
            self.assertIn(f'"{status}"', tasking_text)


if __name__ == "__main__":
    unittest.main()
