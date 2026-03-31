import os
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction
from qgis.core import QgsApplication


class CenterClassifierPlugin:
    """QGIS 플러그인 진입점."""

    def __init__(self, iface) -> None:
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self) -> None:
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QgsApplication.getThemeIcon("/mActionIdentify.svg")

        self.action = QAction(icon, "중심지 위계 설정", self.iface.mainWindow())
        self.action.setToolTip("중심지 위계 설정: 공간 교차 분석 및 중심지 분류")
        self.action.triggered.connect(self.run)

        self.iface.addPluginToVectorMenu("중심지 위계 설정", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self) -> None:
        self.iface.removePluginVectorMenu("중심지 위계 설정", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dialog:
            self.dialog.close()

    def run(self) -> None:
        from .dialog import CenterClassifierDialog
        if self.dialog is None:
            self.dialog = CenterClassifierDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
