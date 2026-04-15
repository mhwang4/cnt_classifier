from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorLayer,
)

from ..models import AnalysisConfig, ClassifyConfig, Operator
from ..processor import AnalysisCancelledError, SpatialProcessor

_OPERATORS      = ["≥", "≤", "=", ">", "<"]
_OPERATOR_TYPES = [Operator.GTE, Operator.LTE, Operator.EQ, Operator.GT, Operator.LT]


class ClassifyCentersAlgorithm(QgsProcessingAlgorithm):
    """속성 추출 완료된 중심지 후보 레이어에 위계 분류 적용."""

    INPUT = "INPUT"

    LIVING_FIELD     = "LIVING_FIELD"
    LIVING_OP        = "LIVING_OP"
    LIVING_THRESHOLD = "LIVING_THRESHOLD"

    REGIONAL_FIELD     = "REGIONAL_FIELD"
    REGIONAL_OP        = "REGIONAL_OP"
    REGIONAL_THRESHOLD = "REGIONAL_THRESHOLD"

    METRO_FIELD1     = "METRO_FIELD1"
    METRO_OP1        = "METRO_OP1"
    METRO_THRESHOLD1 = "METRO_THRESHOLD1"

    METRO_FIELD2     = "METRO_FIELD2"
    METRO_OP2        = "METRO_OP2"
    METRO_THRESHOLD2 = "METRO_THRESHOLD2"

    EMD_LAYER      = "EMD_LAYER"
    DELETE_OUTSIDE = "DELETE_OUTSIDE"

    # ---- 메타데이터 -------------------------------------------------------- #

    def name(self) -> str:
        return "classify_centers"

    def displayName(self) -> str:
        return "중심지 추출 및 위계 설정"

    def group(self) -> str:
        return ""

    def groupId(self) -> str:
        return ""

    def shortHelpString(self) -> str:
        return (
            "속성이 추출된 중심지 후보 레이어에 분류 기준을 적용하여\n"
            "광역중심지 / 지역중심지 / 생활중심지 / 이외로 위계를 설정합니다.\n\n"
            "분류 체계 (cascade):\n"
            "  ① 생활중심지 조건 충족 → 생활중심지\n"
            "  ② + 지역중심지 조건 충족 → 지역중심지\n"
            "  ③ + 광역중심지 AND 조건 충족 → 광역중심지\n"
            "  ④ 생활중심지 조건 미충족 → 이외\n\n"
            "입력: '중심지 후보 속성 추출' 알고리즘의 출력 레이어\n"
            "처리: 입력 GeoPackage 파일에 '분류' 필드를 직접 추가·업데이트합니다."
        )

    def createInstance(self):
        return ClassifyCentersAlgorithm()

    # ---- 파라미터 정의 ----------------------------------------------------- #

    def initAlgorithm(self, config=None) -> None:
        # 입력 레이어 (속성 포함 중심지 후보)
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.INPUT, "중심지 후보(속성 포함) 레이어",
            types=[QgsProcessing.TypeVectorPolygon],
        ))

        # 생활중심지 조건
        self.addParameter(QgsProcessingParameterField(
            self.LIVING_FIELD, "생활중심지 조건 필드",
            defaultValue="total_fac_avg_ratio",
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.LIVING_OP, "생활중심지 연산자",
            options=_OPERATORS, defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.LIVING_THRESHOLD, "생활중심지 임계값",
            type=QgsProcessingParameterNumber.Double, defaultValue=0.20,
        ))

        # 지역중심지 추가 조건
        self.addParameter(QgsProcessingParameterField(
            self.REGIONAL_FIELD, "지역중심지 조건 필드",
            defaultValue="base_fac_avg_ratio",
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.REGIONAL_OP, "지역중심지 연산자",
            options=_OPERATORS, defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.REGIONAL_THRESHOLD, "지역중심지 임계값",
            type=QgsProcessingParameterNumber.Double, defaultValue=0.50,
        ))

        # 광역중심지 AND 조건1
        self.addParameter(QgsProcessingParameterField(
            self.METRO_FIELD1, "광역중심지 조건1 필드",
            defaultValue="res_pop_sum",
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.METRO_OP1, "광역중심지 조건1 연산자",
            options=_OPERATORS, defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.METRO_THRESHOLD1, "광역중심지 조건1 임계값",
            type=QgsProcessingParameterNumber.Double, defaultValue=50000.0,
        ))

        # 광역중심지 AND 조건2
        self.addParameter(QgsProcessingParameterField(
            self.METRO_FIELD2, "광역중심지 조건2 필드 (AND)",
            defaultValue="wor_pop_sum",
            parentLayerParameterName=self.INPUT,
            type=QgsProcessingParameterField.Numeric,
            optional=True,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.METRO_OP2, "광역중심지 조건2 연산자",
            options=_OPERATORS, defaultValue=0,
        ))
        self.addParameter(QgsProcessingParameterNumber(
            self.METRO_THRESHOLD2, "광역중심지 조건2 임계값 (AND)",
            type=QgsProcessingParameterNumber.Double, defaultValue=50000.0,
        ))

        # 읍면동 경계 (선택: 같은 읍면동 내 중복 제거)
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.EMD_LAYER,
            "읍면동 경계 (선택: 같은 읍면동 내 거주인구 최대 폴리곤만 유지)",
            optional=True,
        ))

        # '이외' 삭제 여부
        self.addParameter(QgsProcessingParameterBoolean(
            self.DELETE_OUTSIDE, "'이외' 분류 피처 삭제",
            defaultValue=True,
        ))

    # ---- 실행 -------------------------------------------------------------- #

    def processAlgorithm(self, parameters, context, feedback):
        input_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)

        # GeoPackage 파일 경로 추출 ("|layername=..." 제거)
        gpkg_path = input_layer.source().split("|")[0]

        emd_layer = self.parameterAsVectorLayer(parameters, self.EMD_LAYER, context)
        emd_path  = emd_layer.source().split("|")[0] if emd_layer else ""

        ccfg = ClassifyConfig(
            living_field    =self.parameterAsString(parameters, self.LIVING_FIELD,     context) or "total_fac_avg_ratio",
            living_op       =_OPERATOR_TYPES[self.parameterAsEnum(parameters, self.LIVING_OP,        context)],
            living_threshold=self.parameterAsDouble(parameters, self.LIVING_THRESHOLD, context),

            regional_field    =self.parameterAsString(parameters, self.REGIONAL_FIELD,     context) or "base_fac_avg_ratio",
            regional_op       =_OPERATOR_TYPES[self.parameterAsEnum(parameters, self.REGIONAL_OP,        context)],
            regional_threshold=self.parameterAsDouble(parameters, self.REGIONAL_THRESHOLD, context),

            metro_field1    =self.parameterAsString(parameters, self.METRO_FIELD1,     context) or "res_pop_sum",
            metro_op1       =_OPERATOR_TYPES[self.parameterAsEnum(parameters, self.METRO_OP1,        context)],
            metro_threshold1=self.parameterAsDouble(parameters, self.METRO_THRESHOLD1, context),

            metro_field2    =self.parameterAsString(parameters, self.METRO_FIELD2,     context) or "wor_pop_sum",
            metro_op2       =_OPERATOR_TYPES[self.parameterAsEnum(parameters, self.METRO_OP2,        context)],
            metro_threshold2=self.parameterAsDouble(parameters, self.METRO_THRESHOLD2, context),
        )

        config = AnalysisConfig(
            output_path   =gpkg_path,
            emd_layer_path=emd_path,
            classify_cfg  =ccfg,
        )

        processor = SpatialProcessor(config)
        delete_outside = self.parameterAsBoolean(parameters, self.DELETE_OUTSIDE, context)

        def make_cb(start: int, end: int):
            def cb(pct: int, msg: str) -> None:
                scaled = start + int(pct * (end - start) / 100)
                feedback.setProgress(scaled)
                feedback.pushInfo(msg)
                if feedback.isCanceled():
                    processor.cancel_requested = True
            return cb

        try:
            if emd_path:
                processor.execute_dedup(progress_callback=make_cb(0, 30))
                processor.execute_phase2(progress_callback=make_cb(30, 80))
            else:
                processor.execute_phase2(progress_callback=make_cb(0, 80))

            if delete_outside:
                n = processor.execute_delete_outside(progress_callback=make_cb(80, 100))
                feedback.pushInfo(f"'이외' 피처 {n}개 삭제")
            else:
                feedback.setProgress(100)

        except AnalysisCancelledError:
            feedback.pushWarning("분류가 취소되었습니다.")
            return {}

        feedback.pushInfo("분류 완료")
        return {}
