from typing import List, Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsApplication

from ..models import AnalysisConfig, ClassifyConfig, Operator
from ..worker import ClassifyWorker
from ..renderer import load_and_style_layer
from .tab_input import FileLayerSelector

OPERATORS = ["≥", "≤", "=", ">", "<"]
OPERATOR_MAP = {"≥": Operator.GTE, "≤": Operator.LTE, "=": Operator.EQ,
                ">": Operator.GT, "<": Operator.LT}
OPERATOR_REV = {v: k for k, v in OPERATOR_MAP.items()}


class ConditionWidget(QWidget):
    """단일 조건 행: [필드 드롭다운] [연산자] [임계값]"""

    def __init__(self, label: str, default_field: str,
                 default_op: Operator, default_value: str,
                 field_names: List[str], parent=None) -> None:
        super().__init__(parent)

        self.combo_field = QComboBox()
        self.combo_field.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_field.addItems(field_names)
        idx = self.combo_field.findText(default_field)
        if idx >= 0:
            self.combo_field.setCurrentIndex(idx)

        self.combo_op = QComboBox()
        self.combo_op.addItems(OPERATORS)
        self.combo_op.setCurrentText(OPERATOR_REV.get(default_op, "≥"))
        self.combo_op.setFixedWidth(50)

        self.edit_value = QLineEdit(default_value)
        self.edit_value.setFixedWidth(80)
        self.edit_value.setToolTip("비율은 0~1 사이 값 입력 (예: 0.20 = 20%)")

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addWidget(self.combo_field)
        layout.addWidget(self.combo_op)
        layout.addWidget(self.edit_value)
        layout.addStretch()
        self.setLayout(layout)

    def populate_fields(self, field_names: List[str]) -> None:
        current = self.combo_field.currentText()
        self.combo_field.blockSignals(True)
        self.combo_field.clear()
        self.combo_field.addItems(field_names)
        idx = self.combo_field.findText(current)
        if idx >= 0:
            self.combo_field.setCurrentIndex(idx)
        self.combo_field.blockSignals(False)

    def get_field(self) -> str:
        return self.combo_field.currentText()

    def get_op(self) -> Operator:
        return OPERATOR_MAP.get(self.combo_op.currentText(), Operator.GTE)

    def get_threshold(self) -> float:
        try:
            return float(self.edit_value.text().strip())
        except ValueError:
            return 0.0


class Tab3ClassifyWidget(QWidget):
    """Tab 3: 분류 기준 설정 및 분류 적용."""

    def __init__(self, config: AnalysisConfig, iface, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.iface = iface
        self._worker: Optional[ClassifyWorker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        inner = QWidget()
        inner_layout = QVBoxLayout()
        inner_layout.setSpacing(10)

        # ---- 분류 체계 안내 -------------------------------------------- #
        desc = QGroupBox("분류 체계")
        desc_layout = QVBoxLayout()
        desc_layout.addWidget(QLabel(
            "① <b>생활중심지</b>: 생활중심지 조건 충족\n"
            "② <b>지역중심지</b>: 생활중심지 중 지역중심지 추가 조건 충족\n"
            "③ <b>광역중심지</b>: 지역중심지 중 광역중심지 OR 조건 충족\n"
            "④ <b>이외</b>: 생활중심지 조건 미충족"
        ))
        desc.setLayout(desc_layout)
        inner_layout.addWidget(desc)

        # ---- 출력 파일 참조 (읽기 전용) ---------------------------------- #
        ref_group = QGroupBox("분석 결과 파일")
        self.label_output = QLabel("(Tab 2에서 분석 실행 후 자동으로 표시됩니다)")
        self.label_output.setStyleSheet("color: gray;")
        self.label_output.setWordWrap(True)
        ref_layout = QVBoxLayout()
        ref_layout.addWidget(self.label_output)
        ref_group.setLayout(ref_layout)
        inner_layout.addWidget(ref_group)

        cfg = self.config.classify_cfg

        # ---- 생활중심지 조건 -------------------------------------------- #
        living_group = QGroupBox("생활중심지 조건")
        self.cond_living = ConditionWidget(
            "조건 필드:", cfg.living_field, cfg.living_op,
            str(cfg.living_threshold), [cfg.living_field], self
        )
        living_note = QLabel("기본값: 전체시설 수 평균 비율(total_fac_avg_ratio) ≥ 0.20 (20%)")
        living_note.setStyleSheet("color: gray; font-size: 11px;")
        living_layout = QVBoxLayout()
        living_layout.addWidget(self.cond_living)
        living_layout.addWidget(living_note)
        living_group.setLayout(living_layout)
        inner_layout.addWidget(living_group)

        # ---- 지역중심지 추가 조건 --------------------------------------- #
        regional_group = QGroupBox("지역중심지 추가 조건 (생활중심지 중 적용)")
        self.cond_regional = ConditionWidget(
            "조건 필드:", cfg.regional_field, cfg.regional_op,
            str(cfg.regional_threshold), [cfg.regional_field], self
        )
        regional_note = QLabel("기본값: 거점시설 수 평균 비율(base_fac_avg_ratio) ≥ 0.50 (50%)")
        regional_note.setStyleSheet("color: gray; font-size: 11px;")
        regional_layout = QVBoxLayout()
        regional_layout.addWidget(self.cond_regional)
        regional_layout.addWidget(regional_note)
        regional_group.setLayout(regional_layout)
        inner_layout.addWidget(regional_group)

        # ---- 광역중심지 추가 조건 (OR) ---------------------------------- #
        metro_group = QGroupBox("광역중심지 추가 조건 (지역중심지 중 적용, AND 논리)")
        self.cond_metro1 = ConditionWidget(
            "조건1 필드:", cfg.metro_field1, cfg.metro_op1,
            str(cfg.metro_threshold1), [cfg.metro_field1], self
        )
        or_label = QLabel("그리고 (AND)")
        or_label.setStyleSheet("font-weight: bold; padding: 2px 0;")
        self.cond_metro2 = ConditionWidget(
            "조건2 필드:", cfg.metro_field2, cfg.metro_op2,
            str(cfg.metro_threshold2), [cfg.metro_field2], self
        )
        metro_note = QLabel(
            "기본값: 거주인구 합계(res_pop_sum) ≥ 50000  그리고  근무인구 합계(wor_pop_sum) ≥ 50000"
        )
        metro_note.setStyleSheet("color: gray; font-size: 11px;")
        metro_layout = QVBoxLayout()
        metro_layout.addWidget(self.cond_metro1)
        metro_layout.addWidget(or_label)
        metro_layout.addWidget(self.cond_metro2)
        metro_layout.addWidget(metro_note)
        metro_group.setLayout(metro_layout)
        inner_layout.addWidget(metro_group)

        # ---- 시군구 경계 설정 (선택 사항) ------------------------------- #
        sgg_group = QGroupBox("시군구 경계 설정 (선택 사항)")
        self.sel_sgg = FileLayerSelector(self)
        self.sel_sgg.layer_changed.connect(self._on_sgg_changed)
        sgg_note = QLabel("※ 설정 시: 분류 완료 후 시군구 경계를 지도 뷰에 추가합니다 (채우기 없음, 굵은 경계선).")
        sgg_note.setStyleSheet("color: gray; font-size: 11px;")
        sgg_note.setWordWrap(True)
        sgg_layout = QVBoxLayout()
        sgg_layout.addWidget(self.sel_sgg)
        sgg_layout.addWidget(sgg_note)
        sgg_group.setLayout(sgg_layout)
        inner_layout.addWidget(sgg_group)

        # ---- 읍면동 경계 설정 (선택 사항) ------------------------------- #
        emd_group = QGroupBox("읍면동 경계 설정 (선택 사항)")
        self.sel_emd = FileLayerSelector(self)
        self.sel_emd.layer_changed.connect(self._on_emd_changed)
        emd_note = QLabel(
            "※ 설정 시: 같은 읍면동 내에 중심점이 포함되는 폴리곤 중\n"
            "   거주인구 합계(res_pop_sum)가 가장 많은 폴리곤 1개만 남기고 나머지를 삭제합니다."
        )
        emd_note.setStyleSheet("color: gray; font-size: 11px;")
        emd_note.setWordWrap(True)
        emd_layout = QVBoxLayout()
        emd_layout.addWidget(self.sel_emd)
        emd_layout.addWidget(emd_note)
        emd_group.setLayout(emd_layout)
        inner_layout.addWidget(emd_group)

        inner_layout.addStretch()
        inner.setLayout(inner_layout)
        scroll.setWidget(inner)

        # ---- 진행 표시 -------------------------------------------------- #
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()

        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumHeight(100)
        self.log_widget.hide()

        # ---- 분류 적용 버튼 --------------------------------------------- #
        self.btn_classify = QPushButton("분류 적용")
        self.btn_classify.setFixedHeight(34)
        self.btn_classify.clicked.connect(self._on_classify)

        btn_layout = QHBoxLayout()
        btn_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        btn_layout.addWidget(self.btn_classify)

        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.log_widget)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    # ------------------------------------------------------------------ #

    def populate_field_dropdowns(self, field_names: List[str]) -> None:
        """Tab 2 설정 변경 시 Dialog에서 호출."""
        for cond in [self.cond_living, self.cond_regional,
                     self.cond_metro1, self.cond_metro2]:
            cond.populate_fields(field_names)

        # 기본 필드가 목록에 있으면 선택
        defaults = [
            (self.cond_living,   "total_fac_avg_ratio"),
            (self.cond_regional, "base_fac_avg_ratio"),
            (self.cond_metro1,   "res_pop_sum"),
            (self.cond_metro2,   "wor_pop_sum"),
        ]
        for cond, default in defaults:
            if cond.combo_field.findText(default) >= 0:
                cond.combo_field.setCurrentText(default)

    def _on_sgg_changed(self) -> None:
        self.config.sgg_layer_path = self.sel_sgg.get_path()

    def _on_emd_changed(self) -> None:
        self.config.emd_layer_path = self.sel_emd.get_path()

    def refresh_output_label(self) -> None:
        """Tab 2 분석 완료 후 Dialog에서 호출."""
        path = self.config.output_path
        if path:
            self.label_output.setText(f"📄 {path}")
            self.label_output.setStyleSheet("color: black;")

    # ------------------------------------------------------------------ #

    def _on_classify(self) -> None:
        if not self.config.output_path:
            QMessageBox.warning(self, "경고", "Tab 2에서 먼저 분석을 실행하세요.")
            return

        self._sync_to_config()

        self._worker = ClassifyWorker(self.config)
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.task_completed.connect(self._on_finished)

        self.btn_classify.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.log_widget.clear()
        self.log_widget.show()

        QgsApplication.taskManager().addTask(self._worker)

    def _sync_to_config(self) -> None:
        ccfg = self.config.classify_cfg
        ccfg.living_field     = self.cond_living.get_field()
        ccfg.living_op        = self.cond_living.get_op()
        ccfg.living_threshold = self.cond_living.get_threshold()
        ccfg.regional_field     = self.cond_regional.get_field()
        ccfg.regional_op        = self.cond_regional.get_op()
        ccfg.regional_threshold = self.cond_regional.get_threshold()
        ccfg.metro_field1     = self.cond_metro1.get_field()
        ccfg.metro_op1        = self.cond_metro1.get_op()
        ccfg.metro_threshold1 = self.cond_metro1.get_threshold()
        ccfg.metro_field2     = self.cond_metro2.get_field()
        ccfg.metro_op2        = self.cond_metro2.get_op()
        ccfg.metro_threshold2 = self.cond_metro2.get_threshold()
        self.config.sgg_layer_path = self.sel_sgg.get_path()
        self.config.emd_layer_path = self.sel_emd.get_path()

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress_bar.setValue(pct)
        self.log_widget.appendPlainText(f"[{pct:3d}%] {msg}")

    def _on_finished(self, success: bool, message: str) -> None:
        self.btn_classify.setEnabled(True)
        self.log_widget.appendPlainText(message)
        if success:
            try:
                load_and_style_layer(self.config.output_path)

                if self.config.sgg_layer_path:
                    from ..renderer import add_sgg_layer
                    add_sgg_layer(self.config.sgg_layer_path)

                if self.config.emd_layer_path:
                    from ..renderer import add_emd_layer
                    add_emd_layer(self.config.emd_layer_path)

                QMessageBox.information(
                    self, "완료",
                    "분류가 완료되었습니다.\n"
                    "'중심지유형 분류결과' 레이어가 맵에 추가되었습니다.\n\n"
                    f"{self.config.output_path}"
                )
            except Exception as e:
                QMessageBox.warning(
                    self, "완료 (레이어 로드 실패)",
                    f"분류 저장은 완료되었으나 레이어 로드 중 오류:\n{e}"
                )
        else:
            QMessageBox.critical(self, "오류", message)
