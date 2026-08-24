# Third-party notices

No third-party source code, Python wheel, native library, font file, satellite
image, GeoPackage, or validation dataset is bundled in this repository.

The plugin interoperates at runtime with software supplied by the user's QGIS
installation:

- QGIS/PyQGIS — GNU General Public License;
- GDAL/OGR — generally MIT, with build dependencies subject to their own terms;
- NumPy — modified BSD license;
- PyProj — MIT license;
- Matplotlib — PSF-based/BSD-compatible license.

These projects are not redistributed by this repository. Their authoritative
license terms remain with their respective distributions.

The templates reference common system fonts, including Times New Roman, SimSun,
Microsoft YaHei, and Arial. Font files are not copied or redistributed.

The SAR map may use a north-arrow SVG supplied by the installed QGIS runtime;
that runtime asset is referenced at execution time and is not bundled here.
The repository also contains simple project-local SVG artwork and QPT templates.
The project-local SVG artwork and QPT templates are distributed under
`GPL-2.0-or-later` as recorded in `LICENSING.md`.

Authoritative references:

- https://docs.qgis.org/3.44/en/docs/about/license/index.html
- https://gdal.org/en/stable/license.html
- https://numpy.org/doc/stable/license.html
- https://github.com/pyproj4/pyproj
- https://matplotlib.org/stable/project/license.html
