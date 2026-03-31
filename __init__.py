def classFactory(iface):
    from .plugin import CenterClassifierPlugin
    return CenterClassifierPlugin(iface)
