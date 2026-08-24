# Runtime dependencies

The repository does not vendor third-party Python packages or binary libraries.
The validated runtime is the Python environment shipped with QGIS
3.44.11-Solothurn.

| Dependency | Use | Distribution expectation |
|---|---|---|
| QGIS / PyQGIS / Qt bindings | Plugin lifecycle, UI, layers, projects, layouts, tasks | Provided by QGIS |
| GDAL/OGR/OSR (`osgeo`) | Raster and vector I/O, warping, CRS handling | Provided by QGIS/OSGeo4W |
| NumPy | Numerical arrays, models, statistics, raster operations | Provided by the validated QGIS environment |
| PyProj | Coordinate transformation in cumulative-grid processing | Provided by the validated QGIS environment |
| Matplotlib | QA previews and time-series charts/PDF output | Required for the affected export paths |
| Python standard library | CSV, JSON, SQLite, hashing, paths, statistics | Provided by QGIS Python |

The plugin does not download packages or invoke `pip` automatically. Users of a
custom QGIS build are responsible for ensuring these modules are available.

The only explicit platform-specific paths are optional Windows font fallbacks
(`Microsoft YaHei` and `SimSun`). No font file is bundled. Other platforms may
use Matplotlib/QGIS font fallback and require separate visual validation.

