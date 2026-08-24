from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr, osr

from rs_psinsar_toolkit.geometry_real_core import (
    RealControlPoint,
    fit_transform_model,
    georeference_with_external_gcps,
    predict_map_coordinates,
    validate_real_control_points,
)
from rs_psinsar_toolkit.sar_core import (
    create_display_product,
    sampled_display_statistics,
)
from rs_psinsar_toolkit.sar_workflow import (
    SarJobSettings,
    execute_sar_job,
    preflight_sar_job,
)


def point(identifier: str, pixel: float, line: float, x: float, y: float):
    return RealControlPoint(
        point_id=identifier,
        subset="train",
        pixel=pixel,
        line=line,
        x=x,
        y=y,
        source_file="synthetic.csv",
        source_row=1,
    )


class GeometryModelTests(unittest.TestCase):
    def _grid(self, transform) -> list[RealControlPoint]:
        rows = []
        for index, (pixel, line) in enumerate(
            ([(x, y) for y in (0, 20, 40, 60) for x in (0, 25, 50, 75)]),
            start=1,
        ):
            x, y = transform(float(pixel), float(line))
            rows.append(point(f"P{index:02d}", pixel, line, x, y))
        return rows

    def test_affine_and_polynomial_models_reproduce_training_coordinates(self):
        transforms = {
            "affine": lambda p, l: (500000 + 2.0 * p + 0.2 * l, 2700000 - 0.1 * p - 2.2 * l),
            "polynomial2": lambda p, l: (
                500000 + 2 * p + 0.2 * l + 0.001 * p * p + 0.0005 * p * l,
                2700000 - 0.1 * p - 2.2 * l + 0.0007 * l * l,
            ),
            "polynomial3": lambda p, l: (
                500000 + 2 * p + 0.2 * l + 0.001 * p * p + 0.000001 * p**3,
                2700000 - 0.1 * p - 2.2 * l + 0.0007 * l * l - 0.000001 * l**3,
            ),
        }
        for model, transform in transforms.items():
            with self.subTest(model=model):
                rows = self._grid(transform)
                fit = fit_transform_model(rows, model)
                errors = [
                    np.linalg.norm(
                        predict_map_coordinates(item, fit) - np.asarray([item.x, item.y])
                    )
                    for item in rows
                ]
                self.assertLess(max(errors), 1.0e-6)

    def test_tps_interpolates_training_coordinates(self):
        rows = self._grid(
            lambda p, l: (
                500000 + 2.0 * p + 0.1 * l + 2.5 * math.sin(p / 20.0),
                2700000 - 0.2 * p - 2.0 * l + 1.5 * math.cos(l / 15.0),
            )
        )
        fit = fit_transform_model(rows, "tps")
        errors = [
            np.linalg.norm(
                predict_map_coordinates(item, fit) - np.asarray([item.x, item.y])
            )
            for item in rows
        ]
        self.assertLess(max(errors), 1.0e-6)

    def test_model_specific_minimum_gcps(self):
        rows = self._grid(lambda p, l: (p, l))
        check = [
            RealControlPoint("C1", "check", 5, 5, 5, 5, "c.csv", 1),
            RealControlPoint("C2", "check", 35, 25, 35, 25, "c.csv", 2),
            RealControlPoint("C3", "check", 65, 55, 65, 55, "c.csv", 3),
        ]
        result = validate_real_control_points(rows[:7], check, 100, 100, "polynomial2")
        self.assertTrue(result["errors"])
        self.assertTrue(any("8" in item for item in result["errors"]))

    def test_gdal_warp_accepts_every_supported_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "unreferenced.tif"
            dataset = gdal.GetDriverByName("GTiff").Create(
                str(source), 80, 70, 1, gdal.GDT_Byte
            )
            dataset.GetRasterBand(1).WriteArray(
                np.arange(80 * 70, dtype=np.uint8).reshape(70, 80)
            )
            dataset = None
            rows = self._grid(
                lambda p, l: (500000 + 10.0 * p, 2700000 - 10.0 * l)
            )
            for model in ("affine", "polynomial2", "polynomial3", "tps"):
                with self.subTest(model=model):
                    output = root / f"{model}.tif"
                    info = georeference_with_external_gcps(
                        source,
                        output,
                        rows,
                        "EPSG:32650",
                        resampling="near",
                        x_resolution=10.0,
                        y_resolution=10.0,
                        run_id=model,
                        transform_model=model,
                    )
                    self.assertTrue(output.is_file())
                    self.assertEqual(info["crs"], "EPSG:32650")


class SarDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source_db.tif"
        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(str(self.source), 64, 48, 1, gdal.GDT_Float32)
        dataset.SetGeoTransform((500000, 10, 0, 2700000, 0, -10))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32650)
        dataset.SetProjection(srs.ExportToWkt())
        array = np.linspace(-25.0, 2.0, 64 * 48, dtype=np.float32).reshape(48, 64)
        array[:4, :] = -9999.0
        array[:, :3] = -9999.0
        band = dataset.GetRasterBand(1)
        band.SetNoDataValue(-9999.0)
        band.WriteArray(array)
        dataset = None

    def tearDown(self):
        self.temp.cleanup()

    def test_all_display_statistics_are_valid(self):
        for method in ("percentile", "minmax", "stddev", "equalize", "centered"):
            with self.subTest(method=method):
                stats = sampled_display_statistics(self.source, method=method)
                self.assertLess(stats["display_minimum"], stats["display_maximum"])
                self.assertGreater(stats["sample_count"], 0)

    def test_rgba_pseudocolor_and_feather_product(self):
        output = self.root / "display.tif"
        stats = sampled_display_statistics(self.source, method="equalize")
        info = create_display_product(
            self.source,
            output,
            statistics=stats,
            color_mode="pseudocolor",
            color_ramp="viridis",
            brightness=5,
            contrast=10,
            gamma=1.1,
            feather_pixels=3,
        )
        self.assertEqual(info["band_count"], 4)
        self.assertTrue(output.is_file())
        dataset = gdal.Open(str(output))
        self.assertEqual(
            dataset.GetMetadataItem("PURPOSE"),
            "8-bit visualization only; scientific source unchanged",
        )
        alpha = dataset.GetRasterBand(4).ReadAsArray()
        self.assertEqual(int(alpha[0, 0]), 0)
        self.assertGreater(int(alpha[20, 20]), 0)
        dataset = None


class SarWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.srs = osr.SpatialReference()
        self.srs.ImportFromEPSG(32650)

    def tearDown(self):
        self.temp.cleanup()

    def _raster(self, name: str, x_origin: float, value: float) -> Path:
        path = self.root / name
        dataset = gdal.GetDriverByName("GTiff").Create(
            str(path), 32, 24, 1, gdal.GDT_Float32
        )
        dataset.SetGeoTransform((x_origin, 10, 0, 2700000, 0, -10))
        dataset.SetProjection(self.srs.ExportToWkt())
        band = dataset.GetRasterBand(1)
        band.SetNoDataValue(-9999.0)
        array = np.full((24, 32), value, dtype=np.float32)
        array[:2, :] = -9999.0
        band.WriteArray(array)
        dataset = None
        return path

    def _mask(self) -> Path:
        return self._mask_at("mask.gpkg", 500000)

    def _mask_at(self, name: str, x_origin: float) -> Path:
        path = self.root / name
        dataset = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
        layer = dataset.CreateLayer("mask", self.srs, ogr.wkbPolygon)
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for x, y in (
            (x_origin, 2700000),
            (x_origin + 500, 2700000),
            (x_origin + 500, 2699760),
            (x_origin, 2699760),
            (x_origin, 2700000),
        ):
            ring.AddPoint(x, y)
        polygon = ogr.Geometry(ogr.wkbPolygon)
        polygon.AddGeometry(ring)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(polygon)
        layer.CreateFeature(feature)
        feature = None
        dataset = None
        return path

    def test_nonintersecting_preflight_reports_both_bounds(self):
        source = self._raster("nonintersecting.tif", 500000, 10.0)
        mask = self._mask_at("far_mask.gpkg", 600000)
        result = preflight_sar_job(
            SarJobSettings(
                raster_paths=(str(source),),
                mask_path=str(mask),
                output_root=str(self.root),
                acknowledge_linear_power=True,
            )
        )
        self.assertEqual(result["status"], "REJECTED")
        message = "\n".join(result["errors"])
        self.assertIn("500000.000000", message)
        self.assertIn("600000.000000", message)

    def test_complete_sar_workflow_preserves_float_and_adds_display_product(self):
        first = self._raster("first.tif", 500000, 10.0)
        second = self._raster("second.tif", 500180, 100.0)
        mask = self._mask()
        settings = SarJobSettings(
            raster_paths=(str(first), str(second)),
            mask_path=str(mask),
            output_root=str(self.root),
            display_method="equalize",
            color_mode="pseudocolor",
            color_ramp="spectral",
            brightness=3,
            contrast=5,
            gamma=1.1,
            create_display_product=True,
            feather_pixels=2,
            acknowledge_linear_power=True,
            acknowledge_source_order=True,
        )
        result = execute_sar_job(settings, run_id="synthetic_m100_sar")
        db = gdal.Open(result.artifacts["db_raster"])
        display = gdal.Open(result.artifacts["display_raster"])
        self.assertEqual(db.RasterCount, 1)
        self.assertEqual(db.GetRasterBand(1).DataType, gdal.GDT_Float32)
        self.assertEqual(display.RasterCount, 4)
        report = Path(result.report_path).read_text(encoding="utf-8")
        self.assertIn('"scientific_raster_unchanged": true', report)
        self.assertTrue(Path(result.artifacts["user_readme"]).is_file())
        db = display = None

if __name__ == "__main__":
    unittest.main()
