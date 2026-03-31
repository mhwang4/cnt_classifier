from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsProject,
    QgsRendererCategory,
    QgsSingleSymbolRenderer,
    QgsSymbol,
    QgsVectorLayer,
)

# 범주별 색상 (fill color, stroke color)
CATEGORY_STYLES = {
    "광역중심지": (QColor(140, 0,   0,   220), QColor(80,  0,   0)),
    "지역중심지": (QColor(204, 51,  51,  220), QColor(140, 20,  20)),
    "생활중심지": (QColor(255, 153, 0,   220), QColor(180, 100, 0)),
    "이외":       (QColor(180, 180, 180, 180), QColor(120, 120, 120)),
}


def load_and_style_layer(output_path: str) -> QgsVectorLayer:
    """GeoPackage를 로드하고 분류 유형별 주제도를 적용한 뒤 프로젝트에 추가."""
    layer = QgsVectorLayer(
        f"{output_path}|layername=분류결과",
        "중심지유형 분류결과",
        "ogr",
    )
    if not layer.isValid():
        raise ValueError(f"출력 레이어를 로드할 수 없습니다:\n{output_path}")

    _apply_categorized_renderer(layer)
    QgsProject.instance().addMapLayer(layer)
    return layer


def add_geojeom_layer(layer_path: str) -> QgsVectorLayer:
    """국토공간거점지도를 지도에 추가하고 폴리곤 스트로크를 없앰."""
    layer = QgsVectorLayer(layer_path, "국토공간거점지도", "ogr")
    if not layer.isValid():
        raise ValueError(f"국토공간거점지도 레이어를 로드할 수 없습니다:\n{layer_path}")

    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    sym_layer = symbol.symbolLayer(0)
    if hasattr(sym_layer, "setStrokeStyle"):
        sym_layer.setStrokeStyle(Qt.NoPen)
    if hasattr(sym_layer, "setStrokeWidth"):
        sym_layer.setStrokeWidth(0)

    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    QgsProject.instance().addMapLayer(layer)
    return layer


def add_emd_layer(layer_path: str) -> QgsVectorLayer:
    """읍면동 경계를 지도에 추가하고 채우기 없음, 경계선만 표시."""
    layer = QgsVectorLayer(layer_path, "읍면동 경계", "ogr")
    if not layer.isValid():
        raise ValueError(f"읍면동 경계 레이어를 로드할 수 없습니다:\n{layer_path}")

    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    sym_layer = symbol.symbolLayer(0)
    if hasattr(sym_layer, "setBrushStyle"):
        sym_layer.setBrushStyle(Qt.NoBrush)
    if hasattr(sym_layer, "setFillColor"):
        sym_layer.setFillColor(QColor(0, 0, 0, 0))  # 완전 투명
    if hasattr(sym_layer, "setStrokeColor"):
        sym_layer.setStrokeColor(QColor(80, 80, 80))
    if hasattr(sym_layer, "setStrokeWidth"):
        sym_layer.setStrokeWidth(0.5)

    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    QgsProject.instance().addMapLayer(layer)
    return layer


def add_sgg_layer(layer_path: str) -> QgsVectorLayer:
    """시군구 경계를 지도에 추가하고 채우기 없음, 읍면동보다 굵은 경계선 표시."""
    layer = QgsVectorLayer(layer_path, "시군구 경계", "ogr")
    if not layer.isValid():
        raise ValueError(f"시군구 경계 레이어를 로드할 수 없습니다:\n{layer_path}")

    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    sym_layer = symbol.symbolLayer(0)
    if hasattr(sym_layer, "setBrushStyle"):
        sym_layer.setBrushStyle(Qt.NoBrush)
    if hasattr(sym_layer, "setFillColor"):
        sym_layer.setFillColor(QColor(0, 0, 0, 0))
    if hasattr(sym_layer, "setStrokeColor"):
        sym_layer.setStrokeColor(QColor(50, 50, 50))
    if hasattr(sym_layer, "setStrokeWidth"):
        sym_layer.setStrokeWidth(1.5)

    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    QgsProject.instance().addMapLayer(layer)
    return layer


def _apply_categorized_renderer(layer: QgsVectorLayer) -> None:
    categories = []
    for value, (fill_color, stroke_color) in CATEGORY_STYLES.items():
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())

        sym_layer = symbol.symbolLayer(0)
        if hasattr(sym_layer, "setFillColor"):
            sym_layer.setFillColor(fill_color)
            sym_layer.setStrokeColor(stroke_color)
            sym_layer.setStrokeWidth(0.5)
        else:
            symbol.setColor(fill_color)

        symbol.setOpacity(0.85)
        categories.append(QgsRendererCategory(value, symbol, value))

    renderer = QgsCategorizedSymbolRenderer("분류", categories)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
