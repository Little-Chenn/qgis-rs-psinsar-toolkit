"""QGIS entry point for the RS & PS-InSAR toolkit."""


def classFactory(iface):
    """Return the QGIS plugin instance."""
    from .plugin import RsPsInsarToolkitPlugin

    return RsPsInsarToolkitPlugin(iface)
