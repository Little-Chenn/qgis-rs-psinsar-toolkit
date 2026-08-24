"""Run the complete repository test suite from QGIS ``--code``."""

from __future__ import annotations

import io
import json
import platform
import sys
import traceback
import unittest
from datetime import datetime, timezone
from pathlib import Path

from qgis.PyQt.QtCore import QTimer
from qgis.core import Qgis
import qgis.utils


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
OUTPUT = ROOT / "reports" / "qgis_unittest_rc1_local_repo.json"


def run() -> None:
    report = {
        "status": "FAIL",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository": str(ROOT),
        "candidate_version": "0.3.0-rc1",
        "qgis_version": Qgis.QGIS_VERSION,
        "python_version": platform.python_version(),
        "tests_run": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "output": "",
    }
    try:
        sys.path.insert(0, str(ROOT))
        stream = io.StringIO()
        suite = unittest.defaultTestLoader.discover(
            str(TESTS), pattern="test_*.py", top_level_dir=str(TESTS)
        )
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        report.update(
            {
                "status": "PASS" if result.wasSuccessful() else "FAIL",
                "tests_run": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
                "output": stream.getvalue(),
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
