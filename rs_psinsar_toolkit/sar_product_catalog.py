"""Read-only discovery and metadata parsing for packaged SAR products.

The M8.3 adapter deliberately treats the GeoTIFF as the scientific raster and
all neighbouring XML/SAFE/KML files as descriptive companions.  It never
modifies the product directory and it does not claim that same-source KML
bounds are independent geometric control.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .localization import tr


TRANSLATION_CONTEXT = "@default"


def _tr(source_text: str) -> str:
    return tr(TRANSLATION_CONTEXT, source_text)
from typing import Any, Sequence


RASTER_SUFFIXES = {".tif", ".tiff"}


def discover_rasters(folder: str | Path) -> list[Path]:
    """Return GeoTIFFs recursively, preserving a deterministic path order."""

    root = Path(folder).expanduser()
    if not root.is_dir():
        raise ValueError(_tr("输入文件夹不存在：{path}").format(path=root))
    paths = sorted(
        {
            path.resolve()
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in RASTER_SUFFIXES
        },
        key=lambda path: str(path).lower(),
    )
    if not paths:
        raise ValueError(_tr("输入文件夹及其子文件夹中没有GeoTIFF。"))
    return paths


def _find_one(folder: Path, pattern: str) -> Path | None:
    matches = sorted(folder.glob(pattern), key=lambda path: path.name.lower())
    return matches[0].resolve() if matches else None


def _text(root: ET.Element | None, path: str) -> str:
    if root is None:
        return ""
    element = root.find(path)
    return (element.text or "").strip() if element is not None else ""


def _float(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_kml_bounds(path: Path | None) -> dict[str, float] | None:
    if path is None:
        return None
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    values: dict[str, float] = {}
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name in {"north", "south", "east", "west"}:
            number = _float((element.text or "").strip())
            if number is not None:
                values[name] = number
    return values if set(values) == {"north", "south", "east", "west"} else None


def _manifest_value(text: str, tag: str) -> str:
    match = re.search(
        rf"<(?:[A-Za-z0-9_]+:)?{re.escape(tag)}(?:\s[^>]*)?>([^<]+)</",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def read_product_metadata(raster_path: str | Path) -> dict[str, Any]:
    """Read companion metadata for one raster without touching source files."""

    raster = Path(raster_path).expanduser().resolve()
    folder = raster.parent
    annotation = _find_one(folder, "*.xml")
    manifest = _find_one(folder, "manifest.safe")
    kml = _find_one(folder, "map-overlay.kml") or _find_one(folder, "*.kml")
    quicklook = _find_one(folder, "quick-look.png")

    root: ET.Element | None = None
    annotation_error = ""
    if annotation is not None:
        try:
            root = ET.parse(annotation).getroot()
        except (ET.ParseError, OSError) as exc:
            annotation_error = str(exc)

    manifest_text = ""
    if manifest is not None:
        try:
            manifest_text = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            manifest_text = ""

    folder_family = folder.name.split("-", 1)[0].upper()
    mission = _text(root, "./adsHeader/missionId")
    product_type = _text(root, "./adsHeader/productType")
    polarisation = _text(root, "./adsHeader/polarisation")
    mode = _text(root, "./adsHeader/mode")
    start_time = _text(root, "./adsHeader/startTime")
    stop_time = _text(root, "./adsHeader/stopTime")
    pass_direction = _text(root, "./generalAnnotation/productInformation/pass")
    incidence = _float(
        _text(root, "./imageAnnotation/imageInformation/incidenceAngleMidSwath")
    )
    pixel_value = _text(root, "./imageAnnotation/imageInformation/pixelValue")
    output_pixels = _text(root, "./imageAnnotation/imageInformation/outputPixels")
    range_spacing = _float(
        _text(root, "./imageAnnotation/imageInformation/rangePixelSpacing")
    )
    azimuth_spacing = _float(
        _text(root, "./imageAnnotation/imageInformation/azimuthPixelSpacing")
    )

    safe_product_type = _manifest_value(manifest_text, "productType")
    safe_polarisation = _manifest_value(
        manifest_text, "transmitterReceiverPolarisation"
    )
    safe_satellite = _manifest_value(manifest_text, "number")
    calibration_present = bool(
        re.search(
            r"calibration|sigmaNought|betaNought|gammaNought",
            (annotation.read_text(encoding="utf-8", errors="replace") if annotation else "")
            + manifest_text,
            flags=re.IGNORECASE,
        )
    )

    return {
        "raster": str(raster),
        "product_folder": str(folder),
        "folder_product_family": folder_family,
        "annotation_xml": str(annotation) if annotation else None,
        "manifest_safe": str(manifest) if manifest else None,
        "map_overlay_kml": str(kml) if kml else None,
        "quicklook_png": str(quicklook) if quicklook else None,
        "annotation_parse_error": annotation_error or None,
        "mission_id": mission or (f"S1{safe_satellite}" if safe_satellite else ""),
        "product_type": product_type,
        "safe_product_type": safe_product_type,
        "polarisation": polarisation or safe_polarisation,
        "mode": mode,
        "start_time": start_time,
        "stop_time": stop_time,
        "pass_direction": pass_direction.upper(),
        "incidence_angle_mid_swath": incidence,
        "pixel_value": pixel_value,
        "output_pixels": output_pixels,
        "range_pixel_spacing": range_spacing,
        "azimuth_pixel_spacing": azimuth_spacing,
        "calibration_metadata_present": calibration_present,
        "kml_bounds": _parse_kml_bounds(kml),
        "companion_complete": all(
            item is not None for item in (annotation, manifest, kml, quicklook)
        ),
    }


def build_catalog(raster_paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    return [read_product_metadata(path) for path in raster_paths]


def catalog_summary(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    def values(name: str) -> list[str]:
        return sorted({str(item.get(name) or "") for item in records if item.get(name)})

    incidence_values = [
        float(item["incidence_angle_mid_swath"])
        for item in records
        if item.get("incidence_angle_mid_swath") is not None
    ]
    return {
        "product_count": len(records),
        "folder_product_families": values("folder_product_family"),
        "mission_ids": values("mission_id"),
        "product_types": values("product_type"),
        "safe_product_types": values("safe_product_type"),
        "polarisations": values("polarisation"),
        "modes": values("mode"),
        "pass_directions": values("pass_direction"),
        "start_times": values("start_time"),
        "incidence_angle_min": min(incidence_values) if incidence_values else None,
        "incidence_angle_max": max(incidence_values) if incidence_values else None,
        "calibration_metadata_count": sum(
            bool(item.get("calibration_metadata_present")) for item in records
        ),
        "complete_companion_count": sum(
            bool(item.get("companion_complete")) for item in records
        ),
    }
