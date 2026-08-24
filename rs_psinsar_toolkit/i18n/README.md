# Translation resources

The plugin keeps Simplified Chinese as its Qt source language and provides an
English catalog named `rs_psinsar_toolkit_en.ts`. QGIS loads the compiled
`rs_psinsar_toolkit_en.qm` catalog when its user-interface language starts with
`en`.

Update the catalog with QGIS 3.44.11 `pylupdate5 -tr-function _tr`, review it
in Qt Linguist, then compile it with Qt 5 `lrelease`. Do not hand-edit a
generated `.qm` file.

QPT layout templates and Markdown documentation are localized separately;
their text is not extracted into this catalog.
