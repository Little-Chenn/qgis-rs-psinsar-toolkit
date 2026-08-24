# Open-source pre-publication audit

Audit date: 2026-08-24  
Local candidate: `0.3.0-rc1`  
Qualified functional baseline: `0.3.0-dev.8` bilingual RC3  
Validated QGIS runtime: `3.44.11-Solothurn`

## Executive result

Technical status: **PASS**.  
Publication status: **GATED — explicit authorization for external publication has not been given**.

The local preparation repository is technically suitable for final review. It
contains the GPL software license, the CC BY 4.0 documentation notice, confirmed
author/contact/repository metadata, and the accepted bilingual plugin tree. The
formal local RC1 ZIP has been built and validated. No GitHub remote has been
configured, and nothing has been uploaded or published.

## Confirmed rights and identity

- Copyright year: 2026
- Author: Yang Chenxi (杨晨曦)
- Affiliation: Xiamen University Joint Remote Sensing Receiving Station
  (厦门大学联合遥感接收站)
- Public contact: `cyang5533@gmail.com`
- Planned repository name: `qgis-rs-psinsar-toolkit`
- GitHub owner: `Little-Chenn`
- Planned repository URL:
  `https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit`
- Public candidate version: `0.3.0-rc1`
- Software, tests, tools, QPT templates, SVG assets, Qt translation resources,
  and other runtime resources: `GPL-2.0-or-later`
- English and Chinese documentation: `CC BY 4.0`

The affiliation identifies the author's stated institutional affiliation. It
does not assert institutional copyright ownership, sponsorship, endorsement,
or official publication by Xiamen University.

## Audited scope

Included:

- 59-file plugin tree promoted from the accepted dev.8/RC3 baseline;
- Chinese/English Qt catalogs and bilingual documentation;
- six Chinese/English QPT templates and project-local SVG assets;
- repository policies, licenses, audit/build tools, and tests.

Excluded from the source repository:

- dev.6 source and all historical release candidates;
- raw imagery, GeoPackages, validation inputs, and reference outputs;
- local QGIS profiles, screenshots, caches, logs, and `.pyc` files;
- formal `0.3.0-rc1` ZIP and locally generated validation outputs, which remain
  local build/evidence artifacts and are ignored by Git.

## Validation evidence

### RC3 qualification accepted by the user

The dev.8 bilingual RC3 passed fresh installation in QGIS 3.44.11, all six
modules, three thematic-map workflows, 39 installed-copy tests, and bilingual
numeric consistency. The user subsequently confirmed the RC3 manual install,
six-module, and three-map acceptance as passed.

### RC1 promotion and installed-copy checks

- Static documentation/metadata/i18n checks: **11/11 PASS**.
- Qualified-baseline comparison: **PASS**.
- Plugin file names: identical 59-file set.
- Runtime Python files: byte-identical to dev.8 except `version.py`.
- Qt `.ts`/`.qm` catalogs: byte-identical.
- Three accepted English QPT template hashes: preserved.
- Actual changes relative to the qualified baseline are limited to eight
  approved release/documentation files.
- Final GitHub metadata audit: **PASS** for owner `Little-Chenn` and repository
  `qgis-rs-psinsar-toolkit`.
- Formal local ZIP build: **PASS**, containing 62 manifest-verified files.
- ZIP SHA-256:
  `42A6BE89EE1D84C01A6B37A66E1AEAADDE35878E02CDB2AE533777169DB19031`.
- Fresh-profile native ZIP installation in QGIS 3.44.11: **PASS** in English
  and Chinese.
- Installed-copy plugin load, seven-window GUI smoke test, metadata and
  translation checks: **PASS** in both languages.
- Installed-copy automated suite: **39/39 PASS** in both languages.
- Installed-copy three-map regression: **PASS** for SAR intensity in dB,
  vertical displacement rate in `mm/year`, and cumulative displacement in
  `mm`.
- Accepted QPT hashes and numeric snapshots matched the qualified dev.8/RC3
  baseline.

Machine-readable evidence is stored locally under the Git-ignored `reports/`
directory so profile paths and validation-environment details are not published.

### Unit-source clarification

The Chinese fresh-profile window initially displayed `形变量单位：m` because
the plugin's global QSettings retained a path to the historical dev.6
validation GeoPackage. A read-only database inspection confirmed that all 56
rows of that legacy `time_catalog` are labelled `m`; the accepted RC1
cumulative-displacement fixture labels all 56 rows `mm`. QGIS profiles do not
isolate the plugin's `QSettings("PyQGISProject", "rs_psinsar_toolkit")` values.

This is not an RC1 calculation-unit change: RC1 validation accepts only a
uniform `mm` time catalog, refuses automatic conversion of non-`mm` inputs,
and the installed-copy cumulative map/report regression passed with `mm` and
`D_target - D_initial`. The historical data and the user's global preferences
were left unchanged.

## Privacy, security, and repository hygiene

- no secret, API-key, password, or private-key pattern found;
- no unapproved email address found;
- no personal workspace absolute path found;
- no raw data, package archive, local QGIS database/profile, cache, or compiled
  Python file found;
- no file over 1 MB found;
- no broken local Markdown link found;
- runtime dependencies are documented and are not vendored.

## Scientific boundaries preserved

- SAR output is described as SAR intensity in dB; no Sigma0/Gamma0 calibration
  claim is made.
- Module 1 is external-GCP image-to-map geometric correction with independent
  RMSE assessment; it is not described as Range-Doppler terrain correction.
- PS-InSAR vertical displacement rate uses `mm/year`; cumulative displacement
  uses `mm` and the formula `D_target - D_initial`.
- Multi-point time-series review remains descriptive/manual and is not
  described as automatic anomaly identification.

## Remaining publication gate

The local RC1 source, package, bilingual fresh-install checks, and three-map
regression are complete. External publication remains a separate gated action.
Do not create/connect the GitHub repository, push commits or tags, upload a
release asset, or submit to the QGIS Plugin Repository until the user gives
explicit authorization for the specific external action.

## QGIS references

- <https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/plugins/releasing.html>
- <https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/plugins/plugins.html>
- <https://docs.qgis.org/3.44/en/docs/about/license/index.html>
