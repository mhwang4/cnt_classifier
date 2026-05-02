from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterEnum,
    QgsProcessingOutputVectorLayer,
    QgsProcessing,
    QgsProcessingUtils,
    QgsProcessingException,
    QgsVectorLayer,
    QgsProject,
)
from qgis import processing


class OdMatrixRoadAlgorithm(QgsProcessingAlgorithm):

    INPUT = "INPUT"
    NETWORK_LAYER = "NETWORK_LAYER"
    TYPE_FIELD = "TYPE_FIELD"
    FROM_TYPE = "FROM_TYPE"
    FROM_ID_FIELD = "FROM_ID_FIELD"
    TO_TYPE = "TO_TYPE"
    TO_ID_FIELD = "TO_ID_FIELD"
    OUTPUT = "OUTPUT"

    _QNEAT3_ALG = "qneat3:OdMatrixFromLayersAsLines"
    _ONEWAY = "ONEWAY"
    _CENTER_TYPES = ["생활중심지", "지역중심지", "광역중심지"]

    def name(self) -> str:
        return "od_matrix_road_distance"

    def displayName(self) -> str:
        return "중심지-중심지 거리(도로) 행렬 산출"

    def group(self) -> str:
        return "중심지 분석"

    def groupId(self) -> str:
        return "center_analysis"

    def createInstance(self):
        return OdMatrixRoadAlgorithm()

    def initAlgorithm(self, config=None) -> None:
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                "중심지 대표점 레이어",
                types=[QgsProcessing.TypeVectorPoint],
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.NETWORK_LAYER,
                "네트워크 레이어 (KTDB GIS 도로망도, UTM-K(EPSG:5179) 좌표계)",
                types=[QgsProcessing.TypeVectorLine],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.TYPE_FIELD,
                "중심지 유형 필드",
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.String,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.FROM_TYPE,
                "기점 중심지 유형",
                options=self._CENTER_TYPES,
                allowMultiple=True,
                defaultValue=[0],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FROM_ID_FIELD,
                "기점 고유 ID 필드",
                parentLayerParameterName=self.INPUT,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.TO_TYPE,
                "종점 중심지 유형",
                options=self._CENTER_TYPES,
                allowMultiple=True,
                defaultValue=[1],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.TO_ID_FIELD,
                "종점 고유 ID 필드",
                parentLayerParameterName=self.INPUT,
            )
        )
        self.addOutput(
            QgsProcessingOutputVectorLayer(
                self.OUTPUT,
                "OD 행렬 결과 레이어",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        center_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        network_layer = self.parameterAsVectorLayer(parameters, self.NETWORK_LAYER, context)
        type_field = self.parameterAsString(parameters, self.TYPE_FIELD, context)
        from_types = [self._CENTER_TYPES[i] for i in self.parameterAsEnums(parameters, self.FROM_TYPE, context)]
        from_id = self.parameterAsString(parameters, self.FROM_ID_FIELD, context)
        to_types = [self._CENTER_TYPES[i] for i in self.parameterAsEnums(parameters, self.TO_TYPE, context)]
        to_id = self.parameterAsString(parameters, self.TO_ID_FIELD, context)

        net_fields = [f.name() for f in network_layer.fields()]
        if self._ONEWAY not in net_fields:
            raise QgsProcessingException(
                f"네트워크 레이어에 '{self._ONEWAY}' 필드가 없습니다. "
                f"현재 필드 목록: {', '.join(net_fields[:30])}"
            )

        from_layer = self._make_filtered_layer(center_layer, type_field, from_types, "기점")
        to_layer = self._make_filtered_layer(center_layer, type_field, to_types, "종점")

        if from_layer.featureCount() == 0:
            raise QgsProcessingException(
                f"기점 피처 없음: 유형 필드='{type_field}', 값={from_types}"
            )
        if to_layer.featureCount() == 0:
            raise QgsProcessingException(
                f"종점 피처 없음: 유형 필드='{type_field}', 값={to_types}"
            )

        feedback.pushInfo(f"기점 피처 수: {from_layer.featureCount()}")
        feedback.pushInfo(f"종점 피처 수: {to_layer.featureCount()}")
        feedback.pushInfo("QNEAT3 OD 행렬 계산 시작...")

        result = processing.run(
            self._QNEAT3_ALG,
            {
                "INPUT": network_layer,
                "FROM_POINT_LAYER": from_layer,
                "FROM_ID_FIELD": from_id,
                "TO_POINT_LAYER": to_layer,
                "TO_ID_FIELD": to_id,
                "STRATEGY": 0,                       # Shortest path (distance)
                "ENTRY_COST_CALCULATION_METHOD": 1,  # Planar (projected CRS)
                "DIRECTION_FIELD": self._ONEWAY,
                "VALUE_FORWARD": "1",
                "VALUE_BACKWARD": None,
                "VALUE_BOTH": "0",
                "DEFAULT_DIRECTION": 2,              # Both directions
                "SPEED_FIELD": None,
                "DEFAULT_SPEED": 50.0,
                "TOLERANCE": 0.0,
                "MATRIX_GEOMETRY_TYPE": 0,           # Straight lines
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        self._dest_id = result["OUTPUT"]
        return {self.OUTPUT: self._dest_id}

    def postProcessAlgorithm(self, context, feedback) -> dict:
        dest_id = getattr(self, "_dest_id", None)
        if not dest_id:
            return {}
        layer = QgsProcessingUtils.mapLayerFromString(dest_id, context)
        if layer and layer.isValid():
            layer.setName("중심지-중심지 OD 행렬")
            QgsProject.instance().addMapLayer(layer)
        return {}

    def _make_filtered_layer(self, layer, type_field, type_values, label):
        """유형 값 목록으로 필터링한 임시 메모리 포인트 레이어 반환."""
        value_set = {str(v) for v in type_values}
        tmp = QgsVectorLayer(f"Point?crs={layer.crs().authid()}", label, "memory")
        dp = tmp.dataProvider()
        dp.addAttributes(layer.fields().toList())
        tmp.updateFields()
        feats = [f for f in layer.getFeatures() if str(f[type_field]) in value_set]
        dp.addFeatures(feats)
        return tmp
