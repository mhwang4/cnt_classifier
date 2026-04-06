import os
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QMenu
from qgis.core import QgsApplication


class CenterClassifierPlugin:
    """QGIS 플러그인 진입점."""

    def __init__(self, iface) -> None:
        self.iface = iface
        self.action = None
        self.dialog = None
        self.menu = None
        self.toolbar = None
        self.provider = None

    def initGui(self) -> None:
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QgsApplication.getThemeIcon("/mActionIdentify.svg")

        self.action = QAction(icon, "중심지 위계 설정", self.iface.mainWindow())
        self.action.setToolTip("중심지 위계 설정: 공간 교차 분석 및 중심지 분류")
        self.action.triggered.connect(self.run)

        # 독립 최상위 메뉴 등록 (Help 메뉴 앞)
        self.menu = QMenu("KRIHS 공간구조 분석/시뮬레이션", self.iface.mainWindow())
        self.menu.addAction(self.action)
        menu_bar = self.iface.mainWindow().menuBar()
        menu_bar.insertMenu(menu_bar.actions()[-1], self.menu)

        # 전용 툴바 등록
        self.toolbar = self.iface.addToolBar("KRIHS 공간구조 분석/시뮬레이션")
        self.toolbar.setObjectName("KRIHSSpaceAnalysisToolBar")
        self.toolbar.addAction(self.action)

        # Processing Provider 등록
        from .processing.provider import CntClassifierProvider
        self.provider = CntClassifierProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self) -> None:
        self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())
        self.menu.deleteLater()
        self.toolbar.deleteLater()
        if self.dialog:
            self.dialog.close()
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    def run(self) -> None:
        from .dialog import CenterClassifierDialog
        if self.dialog is None:
            self.dialog = CenterClassifierDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
