from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterFeatureSink,
    QgsProcessing,
    QgsProcessingUtils,
    QgsWkbTypes,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsCoordinateTransform,
    QgsProject,
    QgsFeatureSink,
)

from ..utils import safe_float


class PopWeightedCentroidAlgorithm(QgsProcessingAlgorithm):

    INPUT = "INPUT"
    GEOJEOM_LAYER = "GEOJEOM_LAYER"
    POP_FIELD = "POP_FIELD"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "pop_weighted_centroid"

    def displayName(self) -> str:
        return "인구가중 중심지 대표점 추출"

    def group(self) -> str:
        return "중심지 분석"

    def groupId(self) -> str:
        return "center_analysis"

    def createInstance(self):
        return PopWeightedCentroidAlgorithm()

    def initAlgorithm(self, config=None) -> None:
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                "중심지 레이어",
                types=[QgsProcessing.TypeVectorPolygon],
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.GEOJEOM_LAYER,
                "국토공간거점지도 레이어",
                types=[QgsProcessing.TypeVectorPolygon],
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.POP_FIELD,
                "인구 가중치 필드",
                parentLayerParameterName=self.GEOJEOM_LAYER,
                type=QgsProcessingParameterField.Numeric,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "인구가중 중심점",
                type=QgsProcessing.TypeVectorPoint,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        center_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        geojeom_layer = self.parameterAsVectorLayer(parameters, self.GEOJEOM_LAYER, context)
        pop_field = self.parameterAsString(parameters, self.POP_FIELD, context)

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            center_layer.fields(),
            QgsWkbTypes.Point,
            center_layer.crs(),
        )
        self._dest_id = dest_id

        feedback.pushInfo("공간 인덱스 구축 중...")
        geojeom_index = QgsSpatialIndex(geojeom_layer.getFeatures())
        geojeom_by_fid = {f.id(): f for f in geojeom_layer.getFeatures()}

        # center → geojeom 변환, geojeom → center 역변환
        to_geojeom = None
        to_center = None
        if center_layer.crs() != geojeom_layer.crs():
            to_geojeom = QgsCoordinateTransform(
                center_layer.crs(), geojeom_layer.crs(), QgsProject.instance()
            )
            to_center = QgsCoordinateTransform(
                geojeom_layer.crs(), center_layer.crs(), QgsProject.instance()
            )

        total = center_layer.featureCount() or 1
        for i, center_feat in enumerate(center_layer.getFeatures()):
            if feedback.isCanceled():
                break
            feedback.setProgress(int(i / total * 100))

            center_geom = center_feat.geometry()

            if to_geojeom:
                geom_t = QgsGeometry(center_geom)
                geom_t.transform(to_geojeom)
            else:
                geom_t = center_geom

            weighted_x = 0.0
            weighted_y = 0.0
            total_weight = 0.0

            for fid in geojeom_index.intersects(geom_t.boundingBox()):
                gf = geojeom_by_fid.get(fid)
                if gf is None:
                    continue
                cell_centroid = gf.geometry().centroid()
                if not geom_t.contains(cell_centroid):
                    continue

                pop = safe_float(gf[pop_field])
                pt = cell_centroid.asPoint()
                weighted_x += pop * pt.x()
                weighted_y += pop * pt.y()
                total_weight += pop

            if total_weight > 0:
                wx = weighted_x / total_weight
                wy = weighted_y / total_weight
                if to_center:
                    result_pt = to_center.transform(QgsPointXY(wx, wy))
                else:
                    result_pt = QgsPointXY(wx, wy)
                point_geom = QgsGeometry.fromPointXY(result_pt)
            else:
                point_geom = center_geom.centroid()
                feedback.pushWarning(
                    f"피처 {center_feat.id()}: 교차 격자 없음 또는 인구 합계 0 → 폴리곤 센트로이드 사용"
                )

            out_feat = QgsFeature(center_layer.fields())
            out_feat.setGeometry(point_geom)
            out_feat.setAttributes(center_feat.attributes())
            sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: dest_id}

    def postProcessAlgorithm(self, context, feedback) -> dict:
        dest_id = getattr(self, "_dest_id", None)
        if dest_id:
            layer = QgsProcessingUtils.mapLayerFromString(dest_id, context)
            if layer and layer.isValid():
                QgsProject.instance().addMapLayer(layer)
        return {}
