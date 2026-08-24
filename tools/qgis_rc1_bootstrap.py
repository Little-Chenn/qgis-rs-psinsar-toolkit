"""Capture QGIS startup-code entry and schedule the RC1 regression safely."""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from qgis.PyQt.QtCore import QTimer
import qgis.utils


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools" / "qgis_rc1_native_install_regression.py"
OUTPUT = ROOT / "reports" / "qgis_bootstrap_rc1.json"


def write(status: str, **details: object) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {"status": status, "startup_code_entered": True, **details},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


try:
    namespace = {"__file__": str(TARGET), "__name__": "__main__"}
    exec(compile(TARGET.read_text(encoding="utf-8"), str(TARGET), "exec"), namespace)
    write("SCHEDULED", target="qgis_rc1_native_install_regression.py")
except Exception:
    write("FAIL", traceback=traceback.format_exc())
    if qgis.utils.iface is not None:
        QTimer.singleShot(0, qgis.utils.iface.actionExit().trigger)
