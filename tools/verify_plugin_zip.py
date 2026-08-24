"""Independently verify the locally built QGIS plugin ZIP and manifest."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VERSION = "0.3.0-rc1"
PLUGIN_ID = "rs_psinsar_toolkit"
ZIP_PATH = DIST / f"{PLUGIN_ID}-{VERSION}.zip"
MANIFEST_PATH = DIST / f"{PLUGIN_ID}-{VERSION}-manifest.json"
OUTPUT = ROOT / "reports" / "package_validation_rc1.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
expected = {
    f"{PLUGIN_ID}/{entry['path']}": entry for entry in manifest["files"]
}

with zipfile.ZipFile(ZIP_PATH, "r") as archive:
    corrupt_member = archive.testzip()
    members = [info for info in archive.infolist() if not info.is_dir()]
    names = [info.filename for info in members]
    top_levels = sorted({name.split("/", 1)[0] for name in names})
    member_results = []
    for info in members:
        data = archive.read(info.filename)
        expected_entry = expected.get(info.filename)
        member_results.append(
            {
                "path": info.filename,
                "expected": expected_entry is not None,
                "size_matches": bool(
                    expected_entry and len(data) == expected_entry["size_bytes"]
                ),
                "sha256_matches": bool(
                    expected_entry
                    and sha256_bytes(data) == expected_entry["sha256"]
                ),
            }
        )

checks = {
    "zip_crc_integrity": corrupt_member is None,
    "manifest_status_pass": manifest.get("status") == "PASS",
    "version_is_rc1": manifest.get("version") == VERSION,
    "zip_name_matches_manifest": manifest.get("zip") == ZIP_PATH.name,
    "zip_sha256_matches_manifest": (
        sha256_file(ZIP_PATH) == manifest.get("zip_sha256")
    ),
    "single_top_level_plugin_directory": top_levels == [PLUGIN_ID],
    "file_count_matches_manifest": (
        len(members) == manifest.get("file_count") == len(expected)
    ),
    "member_names_match_manifest": set(names) == set(expected),
    "all_member_sizes_match": all(
        result["size_matches"] for result in member_results
    ),
    "all_member_hashes_match": all(
        result["sha256_matches"] for result in member_results
    ),
    "licenses_and_authors_in_package": all(
        f"{PLUGIN_ID}/{name}" in names
        for name in ("LICENSE", "LICENSE-DOCUMENTATION.md", "AUTHORS.md")
    ),
}

report = {
    "status": "PASS" if all(checks.values()) else "FAIL",
    "candidate_version": VERSION,
    "zip": ZIP_PATH.name,
    "zip_sha256": sha256_file(ZIP_PATH),
    "file_count": len(members),
    "top_level_directories": top_levels,
    "checks": checks,
    "corrupt_member": corrupt_member,
    "unexpected_members": sorted(set(names) - set(expected)),
    "missing_members": sorted(set(expected) - set(names)),
    "member_failures": [
        result
        for result in member_results
        if not (
            result["expected"]
            and result["size_matches"]
            and result["sha256_matches"]
        )
    ],
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
