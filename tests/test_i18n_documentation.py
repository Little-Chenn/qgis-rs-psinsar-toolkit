"""Documentation and metadata gates for the bilingual 0.3.0-rc1 candidate."""

from __future__ import annotations

import configparser
import re
import unittest
from pathlib import Path


DEV_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = DEV_ROOT / "rs_psinsar_toolkit"


class I18nDocumentationTests(unittest.TestCase):
    def test_paired_documentation_exists_and_cross_links(self) -> None:
        pairs = (
            ("README.md", "README_zh-CN.md"),
            ("USER_GUIDE.md", "USER_GUIDE_zh-CN.md"),
            ("INSTALL.md", "INSTALL_zh-CN.md"),
            ("RELEASE_NOTES.md", "RELEASE_NOTES_zh-CN.md"),
        )
        for english_name, chinese_name in pairs:
            english = (PLUGIN_DIR / english_name).read_text(encoding="utf-8")
            chinese = (PLUGIN_DIR / chinese_name).read_text(encoding="utf-8")
            self.assertIn(f"]({chinese_name})", english)
            self.assertIn(f"]({english_name})", chinese)
            self.assertGreater(len(english), 700)
            self.assertGreater(len(chinese), 700)

    def test_english_docs_use_reviewed_module_names(self) -> None:
        readme = (PLUGIN_DIR / "README.md").read_text(encoding="utf-8")
        guide = (PLUGIN_DIR / "USER_GUIDE.md").read_text(encoding="utf-8")
        combined = readme + "\n" + guide
        required = (
            "GCP-based Geometric Correction and Accuracy Assessment",
            "SAR Image Mosaicking, Mask Clipping and Display Enhancement",
            "SAR Intensity Mapping in dB",
            "PS-InSAR Vertical Displacement Rate Mapping",
            "Batch Mapping of PS-InSAR Cumulative Displacement",
            "PS-InSAR Multi-point Displacement Time-series Review",
        )
        for name in required:
            self.assertIn(name, combined)
        self.assertNotIn("QGIS Secondary Development", combined)
        self.assertNotRegex(combined, re.compile(r"SAR Backscatter", re.I))

    def test_scientific_boundaries_are_documented(self) -> None:
        readme = (PLUGIN_DIR / "README.md").read_text(encoding="utf-8")
        notes = (PLUGIN_DIR / "RELEASE_NOTES.md").read_text(
            encoding="utf-8"
        )
        combined = " ".join((readme + "\n" + notes).split())
        self.assertIn("is not Range-Doppler terrain correction", combined)
        self.assertIn("SAR intensity (dB)", combined)
        self.assertIn("Sigma0/Gamma0", combined)
        self.assertIn("D_target - D_initial", combined)
        self.assertIn("50 m grid", combined)
        self.assertIn("manual review", combined)
        self.assertIn("does not automatically identify anomalies", combined)
        self.assertIn("positive values indicate upward motion", combined)
        self.assertIn("negative values indicate downward motion", combined)

    def test_metadata_and_document_versions_are_rc1(self) -> None:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(PLUGIN_DIR / "metadata.txt", encoding="utf-8")
        general = parser["general"]
        self.assertEqual(general["version"], "0.3.0-rc1")
        self.assertEqual(
            general["name"],
            "Remote Sensing and PS-InSAR Processing & Mapping Toolkit",
        )
        self.assertIn("SAR intensity processing and mapping in dB", general["description"])
        self.assertIn("descriptive multi-point time-series review", general["about"])
        for name in (
            "README.md",
            "README_zh-CN.md",
            "INSTALL.md",
            "INSTALL_zh-CN.md",
            "RELEASE_NOTES.md",
            "RELEASE_NOTES_zh-CN.md",
        ):
            self.assertIn(
                "0.3.0-rc1",
                (PLUGIN_DIR / name).read_text(encoding="utf-8"),
            )

    def test_local_markdown_links_resolve(self) -> None:
        pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for document in PLUGIN_DIR.glob("*.md"):
            for target in pattern.findall(document.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                resolved = (document.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(
                    resolved.exists(),
                    f"Broken local link in {document.name}: {target}",
                )

    def test_release_notes_preserve_external_publication_gate(self) -> None:
        notes = (PLUGIN_DIR / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        normalized = " ".join(notes.split())
        self.assertIn("built and validated locally", normalized)
        self.assertIn("No GitHub upload", normalized)
        self.assertIn("External publication requires separate explicit authorization", normalized)


if __name__ == "__main__":
    unittest.main()
