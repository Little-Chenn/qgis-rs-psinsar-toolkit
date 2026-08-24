"""Generate the three accepted map products from the installed RC1 plugin."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import traceback
from pathlib import Path
from typing import Any

from qgis.PyQt.QtCore import QSettings, QTimer
from qgis.core import Qgis, QgsApplication, QgsProject
import qgis.utils


ROOT = Path(__file__).resolve().parents[1]
CONFIG = globals().get("RC1_THREE_MAP_CONFIG", {})
PLUGIN_DIR = (
    Path(QgsApplication.qgisSettingsDirPath())
    / "python"
    / "plugins"
    / "rs_psinsar_toolkit"
)
OUTPUT_ROOT = ROOT / "validation_outputs" / "qgis_three_map_regression_rc1_20260824"
REPORT_PATH = ROOT / "reports" / "qgis_three_map_regression_rc1.json"
FIXTURE_ROOT = Path(str(CONFIG.get("fixture_root", "")))
MANUAL_ROOT = Path(str(CONFIG.get("manual_root", "")))
BASELINE_ROOT = MANUAL_ROOT / "generated_backscatter_user_qgz_round6_20260822"

EXPECTED_TEMPLATE_HASHES = {
    "sar_intensity": "40C81CA450952285C7C9E5D0E47631C81DD8AE43C4D1C6292DA5F32031421E6E",
    "vertical_rate": "ED7A774CBF19292995947D8FBD855AF712FDF35FBEF5397642C4F0E889C8D070",
    "cumulative_displacement": "CD947A50C74133775D3A0E8559F54991A97F1F4352DA0FD960F278C07A868637",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_one(root: Path, name: str) -> Path:
    matches = list(root.rglob(name))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name} below {root}, found {len(matches)}")
    return matches[0]


def same_number(left: Any, right: Any) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1.0e-9)


def numeric_consistency(
    current_sar: dict[str, Any],
    current_rate: dict[str, Any],
    current_cumulative: dict[str, Any],
) -> dict[str, Any]:
    baseline_sar = read_json(find_one(BASELINE_ROOT / "01_sar_intensity", "sar_map_report.json"))
    baseline_rate = read_json(find_one(BASELINE_ROOT / "02_vertical_rate", "m41_build_report.json"))
    baseline_cumulative = read_json(
        find_one(BASELINE_ROOT / "03_cumulative_displacement", "M7.2.2_BATCH_REPORT.json")
    )

    sar_fields = (
        "sample_min",
        "sample_max",
        "sample_p02",
        "sample_median",
        "sample_p98",
        "sample_positive_ratio",
        "sample_zero_ratio",
        "sample_negative_ratio",
    )
    current_sar_stats = current_sar["input"]["inspection"]
    baseline_sar_stats = baseline_sar["input"]["inspection"]
    sar_checks = {
        key: same_number(current_sar_stats[key], baseline_sar_stats[key])
        for key in sar_fields
    }
    sar_checks["input_sha256"] = (
        current_sar["input"]["sha256_before"]
        == baseline_sar["input"]["sha256_before"]
    )
    sar_checks["display_min_db"] = same_number(
        current_sar["layout"]["display_min_db"],
        baseline_sar["layout"]["display_min_db"],
    )
    sar_checks["display_max_db"] = same_number(
        current_sar["layout"]["display_max_db"],
        baseline_sar["layout"]["display_max_db"],
    )

    rate_checks = {
        "input_velocity_sha256": (
            current_rate["input"]["hashes_before"]["velocity"]
            == baseline_rate["input"]["hashes_before"]["velocity"]
        ),
        "feature_count": (
            current_rate["input"]["feature_count"]
            == baseline_rate["input"]["feature_count"]
        ),
        "minimum": same_number(
            current_rate["style"]["minimum"], baseline_rate["style"]["minimum"]
        ),
        "maximum": same_number(
            current_rate["style"]["maximum"], baseline_rate["style"]["maximum"]
        ),
        "edges": current_rate["style"]["edges"] == baseline_rate["style"]["edges"],
    }

    current_period = current_cumulative["grid"]["periods"][0]
    baseline_period = baseline_cumulative["grid"]["periods"][0]
    cumulative_checks = {
        "input_sha256": (
            current_cumulative["grid"]["input_sha256"]
            == baseline_cumulative["grid"]["input_sha256"]
        ),
        "formula": current_cumulative["formula"] == "D_target - D_initial",
        "unit": current_cumulative["unit"] == "mm",
        "aggregation": current_cumulative["aggregation"] == "50 m grid median",
        "feature_count": (
            current_cumulative["grid"]["feature_count"]
            == baseline_cumulative["grid"]["feature_count"]
        ),
        "valid_point_count": (
            current_period["valid_point_count"]
            == baseline_period["valid_point_count"]
        ),
        "full_minimum": same_number(
            current_period["full_minimum_m"], baseline_period["full_minimum_m"]
        ),
        "full_maximum": same_number(
            current_period["full_maximum_m"], baseline_period["full_maximum_m"]
        ),
        "grid_median_minimum": same_number(
            current_period["grid_median_minimum_m"],
            baseline_period["grid_median_minimum_m"],
        ),
        "grid_median_maximum": same_number(
            current_period["grid_median_maximum_m"],
            baseline_period["grid_median_maximum_m"],
        ),
    }
    groups = {
        "sar_intensity": sar_checks,
        "vertical_rate": rate_checks,
        "cumulative_displacement": cumulative_checks,
    }
    return {
        "baseline": str(BASELINE_ROOT),
        "groups": groups,
        "pass": all(all(checks.values()) for checks in groups.values()),
    }


def run() -> None:
    report: dict[str, Any] = {
        "status": "ERROR",
        "qgis_version": Qgis.QGIS_VERSION,
        "profile_name": Path(QgsApplication.qgisSettingsDirPath()).name,
        "plugin_dir": str(PLUGIN_DIR),
        "output_root": str(OUTPUT_ROOT),
        "templates": {},
        "outputs": {},
        "checks": {},
    }
    manager = None
    try:
        required_config = ("fixture_root", "manual_root", "sar_raster")
        missing_config = [key for key in required_config if not CONFIG.get(key)]
        if missing_config:
            raise RuntimeError(
                "RC1_THREE_MAP_CONFIG is missing: " + ", ".join(missing_config)
            )
        if OUTPUT_ROOT.exists():
            raise RuntimeError(f"Refusing to overwrite regression output: {OUTPUT_ROOT}")
        if REPORT_PATH.exists():
            raise RuntimeError(f"Refusing to overwrite regression report: {REPORT_PATH}")
        if not PLUGIN_DIR.is_dir():
            raise RuntimeError(f"Installed plugin directory not found: {PLUGIN_DIR}")
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
        for directory in (
            OUTPUT_ROOT / "01_sar_intensity",
            OUTPUT_ROOT / "02_vertical_rate",
            OUTPUT_ROOT / "03_cumulative_displacement",
        ):
            directory.mkdir()

        sys.path.insert(0, str(PLUGIN_DIR.parent))
        QSettings().setValue("locale/userLocale", "en")

        from rs_psinsar_toolkit.builder import build_map
        from rs_psinsar_toolkit.displacement_batch_builder import run_displacement_batch
        from rs_psinsar_toolkit.displacement_batch_settings import BatchMapSettings, read_time_catalog
        from rs_psinsar_toolkit.localization import TranslationManager
        from rs_psinsar_toolkit.sar_map_builder import build_sar_map
        from rs_psinsar_toolkit.sar_map_settings import SarMapSettings
        from rs_psinsar_toolkit.settings import MapJobSettings

        manager = TranslationManager(PLUGIN_DIR)
        manager.language = "en"
        manager.install()

        templates = {
            "sar_intensity": PLUGIN_DIR / "templates" / "backscatter_template_v1_en.qpt",
            "vertical_rate": PLUGIN_DIR / "templates" / "plugin_overview_template_v5_en.qpt",
            "cumulative_displacement": PLUGIN_DIR / "templates" / "cumulative_displacement_template_v1_en.qpt",
        }
        report["templates"] = {
            key: {"path": str(path), "sha256": sha256(path)}
            for key, path in templates.items()
        }

        basemap = FIXTURE_ROOT / "02_共享验证数据" / "厦门卫星底图.tif"
        sar_raster = Path(str(CONFIG["sar_raster"]))
        rate_vector = (
            FIXTURE_ROOT
            / "06_PS-InSAR垂直形变速率专题制图"
            / "01_输入数据"
            / "50米垂直形变速率网格.gpkg"
        )
        cumulative_gpkg = MANUAL_ROOT / "fixtures" / "cumulative_mm_catalog.gpkg"
        cumulative_basemap = (
            FIXTURE_ROOT
            / "07_PS-InSAR累计形变批量制图"
            / "01_输入数据"
            / "厦门卫星底图.tif"
        )

        sar_result = build_sar_map(
            SarMapSettings(
                raster_path=str(sar_raster),
                output_root=str(OUTPUT_ROOT / "01_sar_intensity"),
                title="BC2 VV SAR Intensity Map in dB",
                show_crs=True,
                crs_text="WGS 84 / UTM zone 50N (EPSG:32650)",
                show_resolution=True,
                resolution_text="3 m",
                show_display_method=True,
                display_method_text="2%–98% linear stretch",
                show_data_source=True,
                data_source="BC2 VV SAR mosaic and clip result",
                show_acquisition_time=False,
                acquisition_time="",
                show_production_date=False,
                production_date="2026-08-24",
                use_current_date=False,
                show_production_unit=False,
                production_unit="",
                export_qgz=True,
                export_png=True,
                export_pdf=False,
                dpi=300,
            ),
            PLUGIN_DIR,
        )

        rate_result = build_map(
            MapJobSettings(
                input_mode="gpkg",
                current_layer_id="",
                current_layer_name="",
                vector_path=str(rate_vector),
                vector_sublayer="velocity_grid",
                value_field="v_median",
                basemap_mode="local_raster",
                local_basemap_path=str(basemap),
                current_basemap_id="",
                current_basemap_name="",
                output_root=str(OUTPUT_ROOT / "02_vertical_rate"),
                title="PS-InSAR Vertical Displacement Rate Map",
                show_data_source=True,
                data_source="Lightweight validation fixture",
                show_acquisition_time=False,
                acquisition_time="",
                show_production_date=False,
                production_date="2026-08-24",
                use_current_date=False,
                show_production_unit=False,
                production_unit="",
                export_qgz=True,
                export_png=True,
                export_pdf=False,
                dpi=150,
            ),
            PLUGIN_DIR,
            source_project=QgsProject(),
        )

        catalog = read_time_catalog(cumulative_gpkg)
        target = next(item for item in catalog if not item.is_initial)
        cumulative_result = run_displacement_batch(
            BatchMapSettings(
                input_gpkg=str(cumulative_gpkg),
                template_path="",
                basemap_path=str(cumulative_basemap),
                output_root=str(OUTPUT_ROOT / "03_cumulative_displacement"),
                selected_fields=(target.field_name,),
                include_initial_map=False,
                title_pattern=(
                    "PS-InSAR Cumulative Vertical Displacement "
                    "({initial_date}–{target_date})"
                ),
                show_data_source=True,
                data_source="PS-InSAR monitoring results",
                show_monitoring_period=True,
                show_production_date=False,
                production_date="2026-08-24",
                show_production_unit=False,
                production_unit="",
                export_qgz=True,
                export_png=True,
                export_pdf=False,
                dpi=150,
                grid_size_m=50.0,
                display_bound_m=20.0,
            ),
            PLUGIN_DIR,
            run_id="formal_rc1_cumulative",
        )

        sar_report = read_json(sar_result.report_path)
        rate_report = read_json(rate_result.report_path)
        cumulative_report = read_json(cumulative_result.report_path)
        numerical = numeric_consistency(sar_report, rate_report, cumulative_report)

        report["outputs"] = {
            "sar_intensity": {
                "status": sar_result.status,
                "png": sar_result.artifacts["png"],
                "qgz": sar_result.artifacts["qgz"],
                "report": str(sar_result.report_path),
            },
            "vertical_rate": {
                "status": rate_result.status,
                "png": rate_result.artifacts["png"],
                "qgz": rate_result.artifacts["qgz"],
                "report": str(rate_result.report_path),
                "unit": rate_report["semantics"]["velocity_unit"],
            },
            "cumulative_displacement": {
                "status": cumulative_result.status,
                "png": str(next(cumulative_result.run_dir.rglob("*.png"))),
                "qgz": str(cumulative_result.qgz_path),
                "report": str(cumulative_result.report_path),
                "unit": cumulative_report["unit"],
                "formula": cumulative_report["formula"],
            },
        }
        report["numeric_consistency"] = numerical
        checks = {
            "qgis_3_44_11": Qgis.QGIS_VERSION.startswith("3.44.11"),
            "installed_profile_matches_config": (
                not CONFIG.get("expected_profile_name")
                or report["profile_name"] == CONFIG["expected_profile_name"]
            ),
            "all_template_hashes_match_acceptance": all(
                report["templates"][key]["sha256"] == expected
                for key, expected in EXPECTED_TEMPLATE_HASHES.items()
            ),
            "sar_pass": sar_result.status == "PASS",
            "vertical_rate_pass": rate_result.status == "PASS",
            "cumulative_displacement_pass": cumulative_result.status == "PASS",
            "sar_is_display_only": sar_report["processing_boundary"]["display_only"] is True,
            "sar_unit_db": sar_report["project_inspection"]["layout_items"]["legend_unit"]["text"] == "Unit: dB",
            "rate_unit_mm_per_year": rate_report["semantics"]["velocity_unit"] == "mm/year",
            "cumulative_unit_mm": cumulative_report["unit"] == "mm",
            "cumulative_formula_unchanged": cumulative_report["formula"] == "D_target - D_initial",
            "all_numeric_snapshots_match": numerical["pass"],
        }
        report["checks"] = checks
        report["status"] = "PASS" if all(checks.values()) else "REVIEW"
    except Exception:
        report["traceback"] = traceback.format_exc()
    finally:
        if manager is not None:
            manager.uninstall()
        QgsProject.instance().clear()
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        if qgis.utils.iface is not None:
            QTimer.singleShot(0, qgis.utils.iface.actionExit().trigger)


QTimer.singleShot(2500, run)
