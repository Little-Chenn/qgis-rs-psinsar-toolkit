"""Build a QGIS plugin ZIP only after publication metadata is complete."""

from __future__ import annotations

import configparser
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "rs_psinsar_toolkit"
LICENSE = ROOT / "LICENSE"
DOCUMENTATION_LICENSE = ROOT / "LICENSE-DOCUMENTATION.md"
AUTHORS = ROOT / "AUTHORS.md"
DIST = ROOT / "dist"
PLUGIN_ID = "rs_psinsar_toolkit"

EXCLUDED_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".bak", ".orig"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


if not LICENSE.is_file() or not LICENSE.read_text(encoding="utf-8").strip():
    raise SystemExit("Publication gate: root LICENSE is missing or empty.")
if (
    not DOCUMENTATION_LICENSE.is_file()
    or not DOCUMENTATION_LICENSE.read_text(encoding="utf-8").strip()
):
    raise SystemExit(
        "Publication gate: LICENSE-DOCUMENTATION.md is missing or empty."
    )
if not AUTHORS.is_file() or not AUTHORS.read_text(encoding="utf-8").strip():
    raise SystemExit("Publication gate: AUTHORS.md is missing or empty.")

metadata = configparser.ConfigParser(interpolation=None)
metadata.read(PLUGIN / "metadata.txt", encoding="utf-8")
general = metadata["general"]
for key in (
    "name", "version", "author", "email", "repository", "homepage", "tracker"
):
    if not general.get(key, "").strip():
        raise SystemExit(f"Publication gate: metadata field {key!r} is empty.")

version = general["version"].strip()
archive_path = DIST / f"{PLUGIN_ID}-{version}.zip"
manifest_path = DIST / f"{PLUGIN_ID}-{version}-manifest.json"
if DIST.exists():
    raise SystemExit(f"Refusing to overwrite existing build directory: {DIST}")
DIST.mkdir()

files: list[tuple[Path, Path]] = []
for path in PLUGIN.rglob("*"):
    if not path.is_file():
        continue
    relative = path.relative_to(PLUGIN)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        continue
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        continue
    files.append((path, relative))
files.append((LICENSE, Path("LICENSE")))
files.append((DOCUMENTATION_LICENSE, Path("LICENSE-DOCUMENTATION.md")))
files.append((AUTHORS, Path("AUTHORS.md")))
files.sort(key=lambda item: item[1].as_posix())

entries: list[dict[str, object]] = []
with zipfile.ZipFile(
    archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
) as archive:
    for source, relative in files:
        archive_name = (Path(PLUGIN_ID) / relative).as_posix()
        archive.write(source, archive_name)
        entries.append(
            {
                "path": relative.as_posix(),
                "size_bytes": source.stat().st_size,
                "sha256": sha256(source),
            }
        )

with zipfile.ZipFile(archive_path, "r") as archive:
    if archive.testzip() is not None:
        raise SystemExit("ZIP integrity check failed.")

manifest = {
    "status": "PASS",
    "plugin_id": PLUGIN_ID,
    "version": version,
    "zip": archive_path.name,
    "zip_sha256": sha256(archive_path),
    "file_count": len(entries),
    "files": entries,
}
manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(manifest, ensure_ascii=False, indent=2))
