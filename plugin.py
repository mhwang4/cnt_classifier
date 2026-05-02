import os
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QMenu
from qgis.core import QgsApplication


class CenterClassifierPlugin:
    """QGIS 플러그인 진입점."""

    def __init__(self, iface) -> None:
        self.iface = iface
        self.menu = None
        self.toolbar = None
        self.provider = None
        self.alg_actions = []

    def initGui(self) -> None:
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QgsApplication.getThemeIcon("/mActionIdentify.svg")

        alg_defs = [
            ("krihs_cnt_classifier:extract_candidates",        "중심지 후보 추출"),
            ("krihs_cnt_classifier:extract_center_attributes", "중심지 후보 속성 추출"),
            ("krihs_cnt_classifier:classify_centers",          "중심지 및 위계 설정"),
        ]
        self.alg_actions = []
        for alg_id, label in alg_defs:
            act = QAction(icon, label, self.iface.mainWindow())
            act.triggered.connect(
                lambda checked=False, aid=alg_id: self._run_algorithm(aid)
            )
            self.alg_actions.append(act)

        # ── 독립 최상위 메뉴 등록 ─────────────────────────────────────
        self.menu = QMenu("KRIHS 공간구조 분석/시뮬레이션", self.iface.mainWindow())
        for act in self.alg_actions:
            self.menu.addAction(act)

        menu_bar = self.iface.mainWindow().menuBar()
        menu_bar.insertMenu(menu_bar.actions()[-1], self.menu)

        # ── 전용 툴바 등록 ────────────────────────────────────────────
        self.toolbar = self.iface.addToolBar("KRIHS 공간구조 분석/시뮬레이션")
        self.toolbar.setObjectName("KRIHSSpaceAnalysisToolBar")
        for act in self.alg_actions:
            self.toolbar.addAction(act)

        # ── Processing Provider 등록 ──────────────────────────────────
        from .processing.provider import CntClassifierProvider
        self.provider = CntClassifierProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self) -> None:
        self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())
        self.menu.deleteLater()
        self.toolbar.deleteLater()
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    def _run_algorithm(self, alg_id: str) -> None:
        from qgis import processing
        processing.execAlgorithmDialog(alg_id)
