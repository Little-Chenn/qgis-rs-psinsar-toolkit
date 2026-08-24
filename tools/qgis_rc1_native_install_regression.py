"""Install the formal RC1 ZIP into a fresh QGIS profile and run smoke tests."""

from __future__ import annotations

import configparser
import hashlib
import io
import json
import platform
import re
import sys
import traceback
import unittest
from datetime import datetime, timezone
from pathlib import Path

from qgis.PyQt.QtCore import QSettings, QTimer
from qgis.PyQt.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTabWidget,
    QWidget,
)
from qgis.core import Qgis, QgsApplication
import qgis.utils


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
PLUGIN_ID = "rs_psinsar_toolkit"
VERSION = "0.3.0-rc1"
ZIP_PATH = ROOT / "dist" / f"{PLUGIN_ID}-{VERSION}.zip"
MANIFEST_PATH = ROOT / "dist" / f"{PLUGIN_ID}-{VERSION}-manifest.json"
PROFILE_NAME = Path(QgsApplication.qgisSettingsDirPath()).name
EXPECTED_LANGUAGE = "zh" if "_zh_" in PROFILE_NAME else "en"
OUTPUT = ROOT / "reports" / (
    "qgis_fresh_install_rc1_zh.json"
    if EXPECTED_LANGUAGE == "zh"
    else "qgis_fresh_install_rc1.json"
)
HAN = re.compile(r"[\u3400-\u9fff]")
WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def visible_texts(window: QWidget) -> list[str]:
    texts: list[str] = []
    for widget in [window, *window.findChildren(QWidget)]:
        if not widget.isVisible():
            continue
        candidates: list[str] = []
        if widget.windowTitle():
            candidates.append(widget.windowTitle())
        if isinstance(widget, (QAbstractButton, QLabel, QGroupBox)):
            candidates.append(widget.text() if hasattr(widget, "text") else widget.title())
        elif isinstance(widget, (QLineEdit, QComboBox)):
            candidates.append(widget.text() if isinstance(widget, QLineEdit) else widget.currentText())
        if isinstance(widget, QTabWidget):
            candidates.extend(widget.tabText(index) for index in range(widget.count()))
        texts.extend(text.strip() for text in candidates if text and text.strip())
    return sorted(set(texts))


def window_snapshot(window: QWidget) -> dict[str, object]:
    texts = visible_texts(window)
    return {
        "window_title": window.windowTitle(),
        "visible": window.isVisible(),
        "size": [window.width(), window.height()],
        "minimum_size": [window.minimumWidth(), window.minimumHeight()],
        "size_hint": [window.sizeHint().width(), window.sizeHint().height()],
        "visible_text_count": len(texts),
        "han_texts": [
            text
            for text in texts
            if HAN.search(text) and not WINDOWS_PATH.match(text)
        ],
    }


def run() -> None:
    report: dict[str, object] = {
        "status": "FAIL",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidate_version": VERSION,
        "qgis_version": Qgis.QGIS_VERSION,
        "python_version": platform.python_version(),
        "profile_name": PROFILE_NAME,
        "expected_language": EXPECTED_LANGUAGE,
        "checks": {},
    }
    try:
        if OUTPUT.exists():
            raise RuntimeError("Refusing to overwrite the existing RC1 QGIS report.")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        settings_dir = Path(QgsApplication.qgisSettingsDirPath())
        plugin_dir = settings_dir / "python" / "plugins" / PLUGIN_ID
        plugin_existed_before = plugin_dir.exists()

        QSettings().setValue(
            "locale/userLocale", "zh_CN" if EXPECTED_LANGUAGE == "zh" else "en"
        )
        from pyplugin_installer import instance as plugin_installer

        native_install_success = plugin_installer().installFromZipFile(str(ZIP_PATH))
        QgsApplication.processEvents()

        installed_files = {
            path.relative_to(plugin_dir).as_posix(): path
            for path in plugin_dir.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix.lower() != ".pyc"
        }
        expected_files = {
            entry["path"]: entry for entry in manifest["files"]
        }
        missing_files = sorted(set(expected_files) - set(installed_files))
        unexpected_files = sorted(set(installed_files) - set(expected_files))
        hash_mismatches = sorted(
            name
            for name in set(expected_files) & set(installed_files)
            if sha256(installed_files[name]) != expected_files[name]["sha256"]
        )

        parser = configparser.ConfigParser(interpolation=None)
        parser.read(plugin_dir / "metadata.txt", encoding="utf-8")
        metadata = parser["general"]
        plugin_instance = qgis.utils.plugins.get(PLUGIN_ID)
        action_text = (
            plugin_instance.action.text()
            if plugin_instance is not None and plugin_instance.action is not None
            else ""
        )

        plugin_instance.run()
        QgsApplication.processEvents()
        hub = plugin_instance.dialog
        hub.open_geometry_correction()
        hub.open_sar_processing()
        hub.open_sar_map()
        hub.open_thematic_map()
        hub.open_displacement_batch()
        hub.open_timeseries_review()
        QgsApplication.processEvents()

        windows = {
            "task_center": window_snapshot(hub),
            "module1_gcp": window_snapshot(hub._geometry_dialog),
            "module2_sar_processing": window_snapshot(hub._sar_dialog),
            "module3_sar_map": window_snapshot(hub._sar_map_dialog),
            "module4_rate_map": window_snapshot(hub._thematic_dialog),
            "module5_cumulative": window_snapshot(hub._displacement_batch_dialog),
            "module6_timeseries": window_snapshot(hub._timeseries_dialog),
        }
        han_texts = sorted(
            {text for window in windows.values() for text in window["han_texts"]}
        )

        sys.path.insert(0, str(plugin_dir.parent))
        sys.path.append(str(ROOT))
        stream = io.StringIO()
        suite = unittest.defaultTestLoader.discover(
            str(TESTS), pattern="test_*.py", top_level_dir=str(TESTS)
        )
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        import rs_psinsar_toolkit

        package_origin = Path(rs_psinsar_toolkit.__file__).resolve().parent
        checks = {
            "qgis_version_3_44_11": Qgis.QGIS_VERSION.startswith("3.44.11"),
            "fresh_profile": not plugin_existed_before,
            "native_zip_installer_success": bool(native_install_success),
            "installed_directory_created": plugin_dir.is_dir(),
            "plugin_available": PLUGIN_ID in qgis.utils.available_plugins,
            "plugin_loaded": qgis.utils.isPluginLoaded(PLUGIN_ID),
            "plugin_instance_created": plugin_instance is not None,
            "plugin_loaded_from_fresh_profile": package_origin == plugin_dir.resolve(),
            "metadata_version_rc1": metadata.get("version") == VERSION,
            "metadata_repository": metadata.get("repository") == (
                "https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit"
            ),
            "metadata_homepage": metadata.get("homepage") == (
                "https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit"
            ),
            "metadata_tracker": metadata.get("tracker") == (
                "https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit/issues"
            ),
            "all_manifest_files_installed": not missing_files,
            "no_unexpected_noncache_files": not unexpected_files,
            "installed_hashes_match_manifest": not hash_mismatches,
            "translator_language_expected": (
                plugin_instance.translation_manager.language == EXPECTED_LANGUAGE
            ),
            "translator_state_expected": (
                (
                    getattr(plugin_instance.translation_manager, "_translator", None)
                    is not None
                )
                if EXPECTED_LANGUAGE == "en"
                else (
                    getattr(plugin_instance.translation_manager, "_translator", None)
                    is None
                )
            ),
            "action_text_expected": action_text == (
                "Open Toolkit" if EXPECTED_LANGUAGE == "en" else "打开工具箱"
            ),
            "seven_windows_opened": all(
                window["visible"] for window in windows.values()
            ),
            "visible_language_expected": (
                not han_texts if EXPECTED_LANGUAGE == "en" else bool(han_texts)
            ),
            "complete_unittest_suite": result.testsRun == 39,
            "unittest_zero_failures": not result.failures,
            "unittest_zero_errors": not result.errors,
            "unittest_zero_skips": not result.skipped,
        }
        report.update(
            {
                "status": "PASS" if all(checks.values()) else "FAIL",
                "checks": checks,
                "zip_sha256": manifest["zip_sha256"],
                "manifest_file_count": manifest["file_count"],
                "installed_file_count": len(installed_files),
                "missing_files": missing_files,
                "unexpected_files": unexpected_files,
                "hash_mismatches": hash_mismatches,
                "action_text": action_text,
                "translator_language": plugin_instance.translation_manager.language,
                "windows": windows,
                "visible_han_texts": han_texts,
                "unittest": {
                    "tests_run": result.testsRun,
                    "failures": len(result.failures),
                    "errors": len(result.errors),
                    "skipped": len(result.skipped),
                    "output": stream.getvalue(),
                },
            }
        )
    except Exception:
        report["traceback"] = traceback.format_exc()
    finally:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if qgis.utils.iface is not None:
            QTimer.singleShot(0, qgis.utils.iface.actionExit().trigger)


QTimer.singleShot(2500, run)
