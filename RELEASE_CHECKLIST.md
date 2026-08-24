# Publication gate checklist

## Author decisions and identity

- [x] Confirm copyright notice and redistribution of project software/resources
      under `GPL-2.0-or-later`.
- [x] Add the complete root `LICENSE` and CC BY 4.0 documentation notice.
- [x] Confirm author, affiliation, copyright year, and public contact email.
- [x] Confirm repository name: `qgis-rs-psinsar-toolkit`.
- [x] Confirm GitHub owner: `Little-Chenn`.
- [x] Add `repository`, `homepage`, and `tracker` metadata URLs for
      `https://github.com/Little-Chenn/qgis-rs-psinsar-toolkit`.
- [x] Confirm first public candidate version: `0.3.0-rc1`.

## Repository review

- [x] No raw imagery, GeoPackage, validation output, local QGIS profile, or ZIP
      is tracked in the preparation tree.
- [x] No secrets, API keys, passwords, private keys, or unapproved email
      addresses found.
- [x] No personal workspace absolute path found in plugin resources/templates.
- [x] Runtime dependencies and scientific boundaries documented.
- [x] `.gitignore`, contribution guidance, security policy, and third-party
      notices prepared.
- [x] License project-local SVG and QPT resources under GPL-2.0-or-later.
- [ ] Decide whether to add a small rights-cleared example dataset separately.
- [ ] Consider a PNG/JPEG plugin icon for maximum QGIS repository compatibility.

## Pre-publication validation

- [x] Run `python tools/build_plugin_zip.py` after final owner URLs were added;
      build the formal local `0.3.0-rc1` ZIP.
- [x] Run 11 static documentation, metadata, i18n, and template-provenance
      checks with zero failures or errors.
- [x] Compare the RC1 source with the qualified dev.8 baseline: identical
      59-file plugin set, runtime code unchanged except `version.py`, Qt
      catalogs unchanged, and three accepted template hashes preserved.
- [x] Record user confirmation that RC3 fresh installation, all six modules,
      and all three thematic maps passed manual acceptance.
- [x] Install the generated ZIP into fresh Chinese and English QGIS 3.44.11
      profiles.
- [x] Run installed-copy plugin load, seven-window GUI smoke checks, three-map
      numeric comparison, and the complete 39-test automated suite in both
      languages. The previously accepted RC3 supplied the manual six-module
      workflow acceptance.
- [x] Record ZIP SHA-256 and a machine-readable 62-file package manifest.
- [x] Review `git diff`, `git status`, and the complete file list after the
      final local audit updates.
- [x] Verify `git remote -v` is empty until explicit publication approval.

## External actions — separate confirmation required

- [ ] Create or connect the GitHub repository.
- [ ] Push the initial branch or tags.
- [ ] Upload a GitHub Release asset.
- [ ] Submit any ZIP to the QGIS Plugin Repository.
