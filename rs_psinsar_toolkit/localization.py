"""Qt translation loading and locale helpers for the plugin."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QSettings, QTranslator


TRANSLATION_BASENAME = "rs_psinsar_toolkit"
SOURCE_LANGUAGE = "zh_CN"
SUPPORTED_TRANSLATIONS = frozenset({"en"})


def qgis_locale_name() -> str:
    """Return the QGIS UI locale, falling back to the operating-system locale."""
    configured = QSettings().value("locale/userLocale", "", type=str).strip()
    locale_name = configured or QLocale.system().name()
    return locale_name.replace("-", "_")


def language_code(locale_name: str | None = None) -> str:
    """Normalize a QGIS locale such as ``en_US`` to its language code."""
    value = (locale_name or qgis_locale_name()).replace("-", "_")
    return value.split("_", 1)[0].lower()


def tr(context: str, source_text: str) -> str:
    """Translate a runtime string while preserving the Chinese source fallback."""
    return QCoreApplication.translate(context, source_text)


class TranslationManager:
    """Own the QTranslator instance for the lifetime of the plugin."""

    def __init__(self, plugin_dir: Path):
        self.plugin_dir = Path(plugin_dir).resolve()
        self.locale_name = qgis_locale_name()
        self.language = language_code(self.locale_name)
        self.catalog_path: Path | None = None
        self._translator: QTranslator | None = None

    @property
    def is_loaded(self) -> bool:
        return self._translator is not None

    def install(self) -> bool:
        """Install the matching compiled catalog, if this locale needs one."""
        if self.is_loaded or self.language not in SUPPORTED_TRANSLATIONS:
            return self.is_loaded
        candidate = (
            self.plugin_dir
            / "i18n"
            / f"{TRANSLATION_BASENAME}_{self.language}.qm"
        )
        if not candidate.is_file():
            return False
        translator = QTranslator()
        if not translator.load(str(candidate)):
            return False
        QCoreApplication.installTranslator(translator)
        self._translator = translator
        self.catalog_path = candidate
        return True

    def uninstall(self) -> None:
        if self._translator is not None:
            QCoreApplication.removeTranslator(self._translator)
            self._translator = None

