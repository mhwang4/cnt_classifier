from typing import Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsVectorLayer

from ..models import AnalysisConfig

VECTOR_FILTER = (
    "벡터 파일 (*.shp *.gpkg *.geojson *.json *.kml *.tab *.gdb);;"
    "Shapefile (*.shp);;"
    "GeoPackage (*.gpkg);;"
    "모든 파일 (*.*)"
)


class FileLayerSelector(QWidget):
    """파일 찾아보기 + GPKG 다중 레이어 선택 콤보."""

    layer_changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layer: Optional[QgsVectorLayer] = None

        self.edit_path = QLineEdit()
        self.edit_path.setReadOnly(True)
        self.edit_path.setPlaceholderText("파일을 선택하세요...")

        self.btn_browse = QPushButton("찾아보기...")
        self.btn_browse.setFixedWidth(90)

        self.combo_sublayer = QComboBox()
        self.combo_sublayer.hide()
        self.combo_sublayer.setToolTip("레이어 선택 (GeoPackage 등 다중 레이어 파일)")

        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.edit_path)
        h.addWidget(self.btn_browse)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(2)
        layout.addLayout(h)
        layout.addWidget(self.combo_sublayer)
        self.setLayout(layout)

        self.btn_browse.clicked.connect(self._on_browse)
        self.combo_sublayer.currentIndexChanged.connect(self._on_sublayer_changed)

    # ------------------------------------------------------------------ #

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "레이어 파일 선택", "", VECTOR_FILTER
        )
        if path:
            self.edit_path.setText(path)
            self._load_from_path(path)

    def _load_from_path(self, path: str) -> None:
        self._layer = None
        layer = QgsVectorLayer(path, "tmp", "ogr")
        if not layer.isValid():
            return

        sublayers = self._vector_sublayers(layer)

        if len(sublayers) > 1:
            self.combo_sublayer.blockSignals(True)
            self.combo_sublayer.clear()
            for name in sublayers:
                self.combo_sublayer.addItem(name)
            self.combo_sublayer.blockSignals(False)
            self.combo_sublayer.show()
            self._on_sublayer_changed(0)
        else:
            self.combo_sublayer.hide()
            self._layer = layer
            self.layer_changed.emit()

    def _on_sublayer_changed(self, idx: int) -> None:
        if idx < 0:
            return
        path = self.edit_path.text()
        name = self.combo_sublayer.currentText()
        uri = f"{path}|layername={name}"
        layer = QgsVectorLayer(uri, "tmp", "ogr")
        if layer.isValid():
            self._layer = layer
            self.layer_changed.emit()

    @staticmethod
    def _vector_sublayers(layer: QgsVectorLayer):
        """벡터 서브레이어 이름 목록 반환."""
        raw = layer.dataProvider().subLayers()
        names = []
        for sl in raw:
            # 형식: "idx!!::!!name!!::!!count!!::!!geomType!!::..."
            parts = sl.split("!!::!!")
            if len(parts) >= 4:
                geom_type = parts[3].strip()
                if geom_type not in ("No geometry", "Unknown geometry", ""):
                    names.append(parts[1].strip())
            elif len(parts) >= 2:
                names.append(parts[1].strip())
        return names if names else [layer.name()]

    # ------------------------------------------------------------------ #

    def get_layer(self) -> Optional[QgsVectorLayer]:
        return self._layer

    def get_path(self) -> str:
        path = self.edit_path.text()
        if self.combo_sublayer.isVisible():
            name = self.combo_sublayer.currentText()
            if name:
                return f"{path}|layername={name}"
        return path

    def is_valid(self) -> bool:
        return self._layer is not None and self._layer.isValid()


# ======================================================================= #

class Tab1InputWidget(QWidget):
    """Tab 1: 입력 파일 직접 선택."""

    layers_ready = pyqtSignal(bool)

    def __init__(self, config: AnalysisConfig, iface, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.iface = iface
        self._build_ui()

    def _build_ui(self) -> None:
        self.sel_center  = FileLayerSelector(self)
        self.sel_geojeom = FileLayerSelector(self)
        self.sel_infra   = FileLayerSelector(self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(6)
        form.addRow("중심지 파일 *",                  self.sel_center)
        form.addRow("국토공간거점지도 파일 *",          self.sel_geojeom)
        form.addRow("생활인프라충족도(500m격자) 파일 *", self.sel_infra)

        group = QGroupBox("입력 레이어 파일 선택")
        group.setLayout(form)

        self.status_label = QLabel("모든 파일을 선택하면 다음 탭이 활성화됩니다.")
        self.status_label.setStyleSheet("color: gray;")

        layout = QVBoxLayout()
        layout.addWidget(group)
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.setLayout(layout)

        for sel in [self.sel_center, self.sel_geojeom, self.sel_infra]:
            sel.layer_changed.connect(self._on_changed)

    def _on_changed(self) -> None:
        ready = all([
            self.sel_center.is_valid(),
            self.sel_geojeom.is_valid(),
            self.sel_infra.is_valid(),
        ])
        if ready:
            self.config.center_layer_path  = self.sel_center.get_path()
            self.config.geojeom_layer_path = self.sel_geojeom.get_path()
            self.config.infra_layer_path   = self.sel_infra.get_path()
            self.status_label.setText("모든 파일이 선택되었습니다. 다음 탭으로 진행하세요.")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("모든 파일을 선택하면 다음 탭이 활성화됩니다.")
            self.status_label.setStyleSheet("color: gray;")

        self.layers_ready.emit(ready)

    def get_layers(self):
        return (
            self.sel_center.get_layer(),
            self.sel_geojeom.get_layer(),
            self.sel_infra.get_layer(),
        )
