"""Run deterministic privacy, content, metadata, and publication-gate checks."""

from __future__ import annotations

import argparse
import ast
import configparser
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "rs_psinsar_toolkit"
IGNORED_PARTS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache",
    "artifacts", "dist", "reports", "validation_outputs",
}
SELF_GENERATED_REPORT = "reports/repository_audit_rc1.json"
FORBIDDEN_SUFFIXES = {
    ".zip", ".tif", ".tiff", ".gpkg", ".shp", ".dbf", ".jp2",
    ".img", ".vrt", ".kmz", ".pyc", ".pyo", ".log", ".tmp",
}
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".xml", ".qpt", ".svg", ".ts",
    ".yml", ".yaml", ".ini", "",
}
SECRET_PATTERNS = {
    "private_key": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY", re.I),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "credential_assignment": re.compile(
        r"\b(api[_-]?key|access[_-]?key|client[_-]?secret|password|passwd)\b\s*[:=]\s*['\"][^'\"]+",
        re.I,
    ),
}
PERSONAL_PATHS = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users|Documents)[\\/]|D:[\\/]PyQGIS[\\/]|/home/[^/]+/|/Users/[^/]+/)",
    re.I,
)
EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
APPROVED_PUBLIC_EMAILS = {"cyang5533@gmail.com"}


def repository_files() -> list[Path]:
    return sorted(
        (
            path for path in ROOT.rglob("*")
            if path.is_file()
            and not any(part in IGNORED_PARTS for part in path.parts)
            and path.relative_to(ROOT).as_posix() != SELF_GENERATED_REPORT
        ),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def read_text(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


files = repository_files()
secrets: list[dict[str, str]] = []
personal_paths: list[str] = []
emails: list[dict[str, str]] = []
broken_links: list[dict[str, str]] = []
link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

for path in files:
    text = read_text(path)
    if text is None:
        continue
    relative = path.relative_to(ROOT).as_posix()
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            secrets.append({"path": relative, "pattern": name})
    # Do not let the scanner's own detection regex trigger a false positive.
    if relative != "tools/audit_repository.py" and PERSONAL_PATHS.search(text):
        personal_paths.append(relative)
    for match in EMAIL.findall(text):
        emails.append({"path": relative, "email": match})
    if path.suffix.lower() == ".md":
        for target in link_pattern.findall(text):
            if "://" in target or target.startswith("#") or target.startswith("mailto:"):
                continue
            destination = (path.parent / target.split("#", 1)[0]).resolve()
            if not destination.exists():
                broken_links.append({"path": relative, "target": target})

imports: set[str] = set()
for path in PLUGIN.rglob("*.py"):
    if any(part in IGNORED_PARTS for part in path.parts):
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module.split(".", 1)[0])

stdlib = set(sys.stdlib_module_names) | {"__future__"}
external_imports = sorted(
    item for item in imports
    if item not in stdlib and not item.startswith("modules")
)

metadata = configparser.ConfigParser(interpolation=None)
metadata.read(PLUGIN / "metadata.txt", encoding="utf-8")
general = metadata["general"]
missing_metadata = [
    key
    for key in ("email", "repository", "homepage", "tracker")
    if not general.get(key, "").strip()
]
license_path = ROOT / "LICENSE"
documentation_license_path = ROOT / "LICENSE-DOCUMENTATION.md"
license_exists = license_path.is_file()
documentation_license_exists = documentation_license_path.is_file()
software_license_text = read_text(license_path) if license_exists else ""
documentation_license_text = (
    read_text(documentation_license_path) if documentation_license_exists else ""
)
unexpected_emails = [
    finding for finding in emails
    if finding["email"].lower() not in APPROVED_PUBLIC_EMAILS
]
forbidden_files = [
    path.relative_to(ROOT).as_posix()
    for path in files
    if path.suffix.lower() in FORBIDDEN_SUFFIXES
]
large_files = [
    {"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size}
    for path in files if path.stat().st_size > 1_000_000
]
blockers = []
if not license_exists:
    blockers.append("Root GPL-2.0-or-later LICENSE is missing.")
if not documentation_license_exists:
    blockers.append("CC BY 4.0 documentation license notice is missing.")
if missing_metadata:
    blockers.append("Required public metadata is incomplete: " + ", ".join(missing_metadata))

technical_checks = {
    "no_secret_patterns": not secrets,
    "no_personal_workspace_paths": not personal_paths,
    "no_unapproved_email_addresses": not unexpected_emails,
    "no_forbidden_data_or_build_files": not forbidden_files,
    "no_files_over_1mb": not large_files,
    "no_broken_local_markdown_links": not broken_links,
    "plugin_metadata_exists": (PLUGIN / "metadata.txt").is_file(),
    "plugin_entrypoint_exists": (PLUGIN / "__init__.py").is_file(),
    "software_license_is_gpl_2_or_later": bool(
        software_license_text
        and "GNU GENERAL PUBLIC LICENSE" in software_license_text
        and "Version 2, June 1991" in software_license_text
    ),
    "documentation_license_is_cc_by_4": bool(
        documentation_license_text
        and "Creative Commons Attribution 4.0 International" in documentation_license_text
    ),
    "candidate_version_is_rc1": general.get("version") == "0.3.0-rc1",
    "approved_public_contact": general.get("email") == "cyang5533@gmail.com",
}

report: dict[str, Any] = {
    "technical_status": "PASS" if all(technical_checks.values()) else "FAIL",
    "publication_status": (
        "BLOCKED_METADATA"
        if blockers
        else "LOCAL_READY_EXTERNAL_APPROVAL_REQUIRED"
    ),
    "external_publication_authorized": False,
    "technical_checks": technical_checks,
    "publication_blockers": blockers,
    "file_count": len(files),
    "plugin_file_count": sum(1 for path in files if PLUGIN in path.parents),
    "external_imports": external_imports,
    "secret_findings": secrets,
    "personal_path_findings": personal_paths,
    "email_findings": emails,
    "unexpected_email_findings": unexpected_emails,
    "forbidden_files": forbidden_files,
    "large_files": large_files,
    "broken_links": broken_links,
    "missing_metadata": missing_metadata,
    "license_exists": license_exists,
    "documentation_license_exists": documentation_license_exists,
    "rights_and_identity": {
        "copyright_year": 2026,
        "author": "Yang Chenxi (杨晨曦)",
        "affiliation": (
            "Xiamen University Joint Remote Sensing Receiving Station "
            "(厦门大学联合遥感接收站)"
        ),
        "software_and_runtime_resources": "GPL-2.0-or-later",
        "english_and_chinese_documentation": "CC BY 4.0",
        "planned_repository_name": "qgis-rs-psinsar-toolkit",
    },
}

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path)
args = parser.parse_args()
serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding="utf-8")
print(serialized, end="")
raise SystemExit(0 if report["technical_status"] == "PASS" else 1)
