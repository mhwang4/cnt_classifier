from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterEnum,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterVectorLayer,
    QgsProject,
    QgsVectorLayer,
)

from ..models import AnalysisConfig, GeojeomConfig, InfraConfig, InfraStatType, StatType
from ..processor import AnalysisCancelledError, SpatialProcessor

# ---- 열거형 옵션 정의 ---------------------------------------------------- #

_POP_STAT_OPTIONS = ["총계(SUM)", "최대(MAX)", "최소(MIN)", "평균(AVG)", "밀도(DENSITY)"]
_POP_STAT_TYPES   = [StatType.SUM, StatType.MAX, StatType.MIN, StatType.AVG, StatType.DENSITY]

_CENT_STAT_OPTIONS = ["최대(MAX)", "최소(MIN)", "평균(AVG)"]
_CENT_STAT_TYPES   = [StatType.MAX, StatType.MIN, StatType.AVG]

_INFRA_AGG_OPTIONS  = ["전체시설", "마을시설", "거점시설"]
_INFRA_STAT_OPTIONS = [
    "평균(AVG)", "최대(MAX)", "최소(MIN)",
    "평균비율(AVG_RATIO)", "최대비율(MAX_RATIO)", "최소비율(MIN_RATIO)",
]
_INFRA_STAT_TYPES = [
    InfraStatType.AVG, InfraStatType.MAX, InfraStatType.MIN,
    InfraStatType.AVG_RATIO, InfraStatType.MAX_RATIO, InfraStatType.MIN_RATIO,
]


class ExtractCenterAttributesAlgorithm(QgsProcessingAlgorithm):
    """중심지 후보(도형) + 격자 2종 → 통계 속성 GeoPackage 생성."""

    CENTER_LAYER  = "CENTER_LAYER"
    GEOJEOM_LAYER = "GEOJEOM_LAYER"
    INFRA_LAYER   = "INFRA_LAYER"

    FIELD_RES_POP = "FIELD_RES_POP"
    FIELD_WOR_POP = "FIELD_WOR_POP"
    FIELD_INFLOW  = "FIELD_INFLOW"
    FIELD_OUTFLOW = "FIELD_OUTFLOW"

    RES_POP_STATS = "RES_POP_STATS"
    WOR_POP_STATS = "WOR_POP_STATS"
    INFLOW_STATS  = "INFLOW_STATS"
    OUTFLOW_STATS = "OUTFLOW_STATS"

    VILLAGE_COLS = "VILLAGE_COLS"
    BASE_COLS    = "BASE_COLS"
    INFRA_AGG    = "INFRA_AGG"
    INFRA_STATS  = "INFRA_STATS"

    OUTPUT = "OUTPUT"

    # ---- 메타데이터 -------------------------------------------------------- #

    def name(self) -> str:
        return "extract_center_attributes"

    def displayName(self) -> str:
        return "중심지 후보 속성 추출"

    def group(self) -> str:
        return ""

    def groupId(self) -> str:
        return ""

    def shortHelpString(self) -> str:
        return (
            "중심지 후보 폴리곤에 대해 국토공간거점지도와 생활인프라충족도 격자 데이터를 "
            "공간 교차 분석하여 인구·중심성·인프라 통계를 추출합니다.\n\n"
            "출력: 통계 필드가 추가된 GeoPackage (GeoPackage 내부 레이어명: 분류결과)\n\n"
            "이 출력을 '중심지 추출 및 위계 설정' 알고리즘의 입력으로 사용합니다."
        )

    def createInstance(self):
        return ExtractCenterAttributesAlgorithm()

    # ---- 파라미터 정의 ----------------------------------------------------- #

    def initAlgorithm(self, config=None) -> None:
        # 입력 레이어
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.CENTER_LAYER, "중심지 후보(도형) 레이어",
            types=[QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.GEOJEOM_LAYER, "국토공간거점지도 레이어",
        ))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INFRA_LAYER, "생활인프라충족도(500m격자) 레이어",
        ))

        # 국토공간거점지도 필드 선택
        for param_name, label, default in [
            (self.FIELD_RES_POP, "거주인구 필드",  "pop_r"),
            (self.FIELD_WOR_POP, "근무인구 필드",  "pop_w"),
            (self.FIELD_INFLOW,  "유입중심성 필드", "pc_in"),
            (self.FIELD_OUTFLOW, "유출중심성 필드", "pc_out"),
        ]:
            self.addParameter(QgsProcessingParameterField(
                param_name, label,
                defaultValue=default,
                parentLayerParameterName=self.GEOJEOM_LAYER,
                type=QgsProcessingParameterField.Numeric,
                optional=True,
            ))

        # 인구 통계 선택
        self.addParameter(QgsProcessingParameterEnum(
            self.RES_POP_STATS, "거주인구 통계",
            options=_POP_STAT_OPTIONS,
            allowMultiple=True,
            defaultValue=list(range(len(_POP_STAT_OPTIONS))),
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.WOR_POP_STATS, "근무인구 통계",
            options=_POP_STAT_OPTIONS,
            allowMultiple=True,
            defaultValue=list(range(len(_POP_STAT_OPTIONS))),
        ))

        # 중심성 통계 선택
        self.addParameter(QgsProcessingParameterEnum(
            self.INFLOW_STATS, "유입중심성 통계",
            options=_CENT_STAT_OPTIONS,
            allowMultiple=True,
            defaultValue=list(range(len(_CENT_STAT_OPTIONS))),
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.OUTFLOW_STATS, "유출중심성 통계",
            options=_CENT_STAT_OPTIONS,
            allowMultiple=True,
            defaultValue=list(range(len(_CENT_STAT_OPTIONS))),
        ))

        # 생활인프라 열 선택
        self.addParameter(QgsProcessingParameterField(
            self.VILLAGE_COLS, "마을시설 열 (복수 선택 가능)",
            parentLayerParameterName=self.INFRA_LAYER,
            type=QgsProcessingParameterField.Any,
            allowMultiple=True,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.BASE_COLS, "거점시설 열 (복수 선택 가능)",
            parentLayerParameterName=self.INFRA_LAYER,
            type=QgsProcessingParameterField.Any,
            allowMultiple=True,
            optional=True,
        ))

        # 인프라 집계 항목 및 통계
        self.addParameter(QgsProcessingParameterEnum(
            self.INFRA_AGG, "인프라 집계 항목",
            options=_INFRA_AGG_OPTIONS,
            allowMultiple=True,
            defaultValue=[0, 1, 2],
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.INFRA_STATS, "인프라 통계",
            options=_INFRA_STAT_OPTIONS,
            allowMultiple=True,
            defaultValue=[0],
        ))

        # 출력
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT, "출력 GeoPackage",
            fileFilter="GeoPackage (*.gpkg)",
        ))

    # ---- 실행 -------------------------------------------------------------- #

    def processAlgorithm(self, parameters, context, feedback):
        center_layer  = self.parameterAsVectorLayer(parameters, self.CENTER_LAYER,  context)
        geojeom_layer = self.parameterAsVectorLayer(parameters, self.GEOJEOM_LAYER, context)
        infra_layer   = self.parameterAsVectorLayer(parameters, self.INFRA_LAYER,   context)

        output_path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        if not output_path.endswith(".gpkg"):
            output_path += ".gpkg"

        # GeojeomConfig 구성
        gcfg = GeojeomConfig(
            field_resident_pop=self.parameterAsString(parameters, self.FIELD_RES_POP, context) or "",
            field_work_pop    =self.parameterAsString(parameters, self.FIELD_WOR_POP, context) or "",
            field_inflow      =self.parameterAsString(parameters, self.FIELD_INFLOW,  context) or "",
            field_outflow     =self.parameterAsString(parameters, self.FIELD_OUTFLOW, context) or "",
            res_pop_stats =[_POP_STAT_TYPES[i]  for i in self.parameterAsEnums(parameters, self.RES_POP_STATS,  context)],
            wor_pop_stats =[_POP_STAT_TYPES[i]  for i in self.parameterAsEnums(parameters, self.WOR_POP_STATS,  context)],
            inflow_stats  =[_CENT_STAT_TYPES[i] for i in self.parameterAsEnums(parameters, self.INFLOW_STATS,   context)],
            outflow_stats =[_CENT_STAT_TYPES[i] for i in self.parameterAsEnums(parameters, self.OUTFLOW_STATS,  context)],
        )

        # InfraConfig 구성
        agg_indices  = self.parameterAsEnums(parameters, self.INFRA_AGG,   context)
        stat_indices = self.parameterAsEnums(parameters, self.INFRA_STATS, context)
        icfg = InfraConfig(
            village_cols   =self.parameterAsFields(parameters, self.VILLAGE_COLS, context),
            base_cols      =self.parameterAsFields(parameters, self.BASE_COLS,    context),
            compute_total  =(0 in agg_indices),
            compute_village=(1 in agg_indices),
            compute_base   =(2 in agg_indices),
            stats          =[_INFRA_STAT_TYPES[i] for i in stat_indices],
        )

        config = AnalysisConfig(
            center_layer_path =center_layer.source(),
            geojeom_layer_path=geojeom_layer.source(),
            infra_layer_path  =infra_layer.source(),
            output_path       =output_path,
            geojeom_cfg       =gcfg,
            infra_cfg         =icfg,
        )

        processor = SpatialProcessor(config)

        def progress_cb(pct: int, msg: str) -> None:
            feedback.setProgress(pct)
            feedback.pushInfo(msg)
            if feedback.isCanceled():
                processor.cancel_requested = True

        try:
            processor.execute(progress_callback=progress_cb)
        except AnalysisCancelledError:
            feedback.pushWarning("분석이 취소되었습니다.")
            return {}

        feedback.pushInfo(f"저장 완료: {output_path}")
        self._output_path = output_path
        return {self.OUTPUT: output_path}

    def postProcessAlgorithm(self, context, feedback):
        output_path = getattr(self, "_output_path", None)
        if not output_path:
            return {}

        layer_uri = f"{output_path}|layername=분류결과"
        layer = QgsVectorLayer(layer_uri, "중심지 후보 속성 추가", "ogr")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
        else:
            feedback.pushWarning("출력 레이어를 지도 뷰에 추가하지 못했습니다.")

        return {}
