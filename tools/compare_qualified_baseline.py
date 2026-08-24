"""Prove that RC1 runtime changes are limited to approved release metadata/docs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "rs_psinsar_toolkit"
BASELINE = ROOT.parent / "i18n_dev8_source" / "rs_psinsar_toolkit"
OUTPUT = ROOT / "reports" / "qualified_baseline_comparison_rc1.json"

APPROVED_RELEASE_CHANGES = {
    "INSTALL.md",
    "INSTALL_zh-CN.md",
    "README.md",
    "README_zh-CN.md",
    "RELEASE_NOTES.md",
    "RELEASE_NOTES_zh-CN.md",
    "metadata.txt",
    "version.py",
}

ACCEPTED_TEMPLATE_HASHES = {
    "templates/backscatter_template_v1_en.qpt":
        "40C81CA450952285C7C9E5D0E47631C81DD8AE43C4D1C6292DA5F32031421E6E",
    "templates/plugin_overview_template_v5_en.qpt":
        "ED7A774CBF19292995947D8FBD855AF712FDF35FBEF5397642C4F0E889C8D070",
    "templates/cumulative_displacement_template_v1_en.qpt":
        "CD947A50C74133775D3A0E8559F54991A97F1F4352DA0FD960F278C07A868637",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.lower() != ".pyc"
    }


baseline_files = files(BASELINE)
current_files = files(CURRENT)
baseline_names = set(baseline_files)
current_names = set(current_files)
common_names = sorted(baseline_names & current_names)
changed = sorted(
    name
    for name in common_names
    if sha256(baseline_files[name]) != sha256(current_files[name])
)
unchanged = sorted(set(common_names) - set(changed))
unexpected_changes = sorted(set(changed) - APPROVED_RELEASE_CHANGES)
missing_approved_changes = sorted(APPROVED_RELEASE_CHANGES - set(changed))
template_hashes = {
    name: sha256(CURRENT / name) for name in ACCEPTED_TEMPLATE_HASHES
}

checks = {
    "same_plugin_file_names": baseline_names == current_names,
    "expected_file_count_59": len(current_names) == len(baseline_names) == 59,
    "only_approved_release_files_changed": not unexpected_changes,
    "all_approved_release_files_changed": not missing_approved_changes,
    "runtime_python_outside_version_unchanged": all(
        name == "version.py" or name in unchanged
        for name in current_names
        if name.endswith(".py")
    ),
    "qt_catalogs_unchanged": all(
        name in unchanged
        for name in (
            "i18n/rs_psinsar_toolkit_en.ts",
            "i18n/rs_psinsar_toolkit_en.qm",
        )
    ),
    "accepted_template_hashes_preserved": template_hashes
    == ACCEPTED_TEMPLATE_HASHES,
}

report = {
    "status": "PASS" if all(checks.values()) else "FAIL",
    "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "qualified_baseline": "i18n_dev8_source/rs_psinsar_toolkit (outside repository)",
    "candidate": "rs_psinsar_toolkit",
    "checks": checks,
    "approved_release_changes": sorted(APPROVED_RELEASE_CHANGES),
    "actual_changed_files": changed,
    "unexpected_changed_files": unexpected_changes,
    "missing_approved_changes": missing_approved_changes,
    "unchanged_file_count": len(unchanged),
    "accepted_template_hashes": template_hashes,
    "qualification_evidence": (
        "i18n_dev8_validation/formal_rc3_install_20260823/reports/"
        "RC3_LOCAL_QUALIFICATION.json (outside repository)"
    ),
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
