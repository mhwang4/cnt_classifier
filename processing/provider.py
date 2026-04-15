import os

from PyQt5.QtGui import QIcon
from qgis.core import QgsApplication, QgsProcessingProvider

from .alg_extract import ExtractCenterAttributesAlgorithm
from .alg_classify import ClassifyCentersAlgorithm
from .alg_extract_candidates import ExtractCandidatesAlgorithm


class CntClassifierProvider(QgsProcessingProvider):

    def id(self) -> str:
        return "krihs_cnt_classifier"

    def name(self) -> str:
        return "KRIHS 공간구조 분석/시뮬레이션"

    def longName(self) -> str:
        return self.name()

    def icon(self) -> QIcon:
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icon.png")
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QgsApplication.getThemeIcon("/mActionIdentify.svg")

    def loadAlgorithms(self) -> None:
        self.addAlgorithm(ExtractCenterAttributesAlgorithm())
        self.addAlgorithm(ClassifyCentersAlgorithm())
        self.addAlgorithm(ExtractCandidatesAlgorithm())
