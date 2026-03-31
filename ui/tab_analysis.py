from typing import Dict, List, Optional

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from qgis.core import QgsApplication, QgsFieldProxyModel, QgsVectorLayer
from qgis.gui import QgsFieldComboBox

from ..models import AnalysisConfig, InfraStatType, StatType
from ..utils import INFRA_STAT_LABEL, STAT_LABEL
from ..worker import AnalysisWorker


# ---- 필드별 통계 선택 행 ----------------------------------------------- #

class FieldStatRow(QWidget):
    changed = pyqtSignal()

    def __init__(self, available_stats: List[StatType], parent=None) -> None:
        super().__init__(parent)
        self.combo = QgsFieldComboBox()
        self.combo.setFilters(QgsFieldProxyModel.Numeric)
        self.combo.setAllowEmptyFieldName(True)

        self.checkboxes: Dict[StatType, QCheckBox] = {}
        cb_layout = QHBoxLayout()
        cb_layout.setContentsMargins(0, 0, 0, 0)
        for stat in available_stats:
            cb = QCheckBox(STAT_LABEL[stat])
            cb.setChecked(True)
            self.checkboxes[stat] = cb
            cb_layout.addWidget(cb)
        cb_layout.addStretch()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 2, 0, 6)
        layout.setSpacing(2)
        layout.addWidget(self.combo)
        layout.addLayout(cb_layout)
        self.setLayout(layout)

        self.combo.fieldChanged.connect(self.changed)
        for cb in self.checkboxes.values():
            cb.stateChanged.connect(self.changed)

    def set_layer(self, layer: QgsVectorLayer) -> None:
        self.combo.setLayer(layer)

    def current_field(self) -> str:
        return self.combo.currentField()

    def selected_stats(self) -> List[StatType]:
        return [s for s, cb in self.checkboxes.items() if cb.isChecked()]


# ---- Tab 2 메인 -------------------------------------------------------- #

class Tab2AnalysisWidget(QWidget):
    settings_changed = pyqtSignal()
    analysis_done = pyqtSignal()   # Phase 1 완료 시 Tab 3 활성화 신호

    def __init__(self, config: AnalysisConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._worker: Optional[AnalysisWorker] = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout()
        inner_layout.setSpacing(12)
        inner_layout.addWidget(self._build_panel_a())
        inner_layout.addWidget(self._build_panel_b())
        inner_layout.addStretch()
        inner.setLayout(inner_layout)
        scroll.setWidget(inner)

        # 출력 경로
        output_group = QGroupBox("출력 파일 설정")
        self.edit_output = QLineEdit()
        self.edit_output.setPlaceholderText("결과 GeoPackage 저장 경로 (.gpkg)")
        self.btn_output = QPushButton("찾아보기...")
        self.btn_output.setFixedWidth(90)
        self.btn_output.clicked.connect(self._on_browse_output)
        out_h = QHBoxLayout()
        out_h.addWidget(QLabel("저장 경로:"))
        out_h.addWidget(self.edit_output)
        out_h.addWidget(self.btn_output)
        output_group.setLayout(out_h)

        # 진행 표시
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()

        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumHeight(100)
        self.log_widget.hide()

        # 분석 버튼
        self.btn_analyze = QPushButton("분석 실행")
        self.btn_analyze.setFixedHeight(34)
        self.btn_analyze.clicked.connect(self._on_analyze)

        btn_layout = QHBoxLayout()
        btn_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        btn_layout.addWidget(self.btn_analyze)

        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        main_layout.addWidget(output_group)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.log_widget)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def _build_panel_a(self) -> QGroupBox:
        group = QGroupBox("국토공간거점지도 설정")
        POP  = [StatType.SUM, StatType.MAX, StatType.MIN, StatType.AVG, StatType.DENSITY]
        CENT = [StatType.MAX, StatType.MIN, StatType.AVG]

        self.row_res_pop = FieldStatRow(POP, self)
        self.row_wor_pop = FieldStatRow(POP, self)
        self.row_inflow  = FieldStatRow(CENT, self)
        self.row_outflow = FieldStatRow(CENT, self)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(4)
        form.addRow("거주인구 필드 *",  self.row_res_pop)
        form.addRow("근무인구 필드 *",  self.row_wor_pop)
        form.addRow("유입중심성 필드 *", self.row_inflow)
        form.addRow("유출중심성 필드 *", self.row_outflow)

        note = QLabel("※ 밀도 = 총계 ÷ 폴리곤 면적(km²), 소수점 2자리 반올림  (CRS가 미터 단위임을 가정)")
        note.setStyleSheet("color: gray; font-size: 11px;")

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(note)
        group.setLayout(layout)

        for row in [self.row_res_pop, self.row_wor_pop, self.row_inflow, self.row_outflow]:
            row.changed.connect(self._on_settings_changed)
        return group

    def _build_panel_b(self) -> QGroupBox:
        group = QGroupBox("생활인프라충족도(500m격자) 설정")

        self.list_village = self._make_list()
        self.list_base    = self._make_list()

        lists_h = QHBoxLayout()
        lists_h.addWidget(self._wrap("마을시설 열 선택 (최대 10개)", self.list_village))
        lists_h.addWidget(self._wrap("거점시설 열 선택 (최대 10개)", self.list_base))

        agg_h = QHBoxLayout()
        agg_h.addWidget(QLabel("집계 항목:"))
        self.cb_total       = QCheckBox("전체시설")
        self.cb_village_agg = QCheckBox("마을시설")
        self.cb_base_agg    = QCheckBox("거점시설")
        for cb in [self.cb_total, self.cb_village_agg, self.cb_base_agg]:
            cb.setChecked(True)
            agg_h.addWidget(cb)
        agg_h.addStretch()

        stat_h = QHBoxLayout()
        stat_h.addWidget(QLabel("통계:"))
        self.infra_stat_cbs: Dict[InfraStatType, QCheckBox] = {}
        for ist in [
            InfraStatType.AVG, InfraStatType.MAX, InfraStatType.MIN,
            InfraStatType.AVG_RATIO, InfraStatType.MAX_RATIO, InfraStatType.MIN_RATIO,
        ]:
            cb = QCheckBox(INFRA_STAT_LABEL[ist])
            cb.setChecked(True)
            self.infra_stat_cbs[ist] = cb
            stat_h.addWidget(cb)
        stat_h.addStretch()

        ratio_note = QLabel(
            "※ 비율: 평균/최대/최소 ÷ 선택된 열 수 "
            "(전체=마을+거점 열 수, 마을/거점=각 열 수)"
        )
        ratio_note.setStyleSheet("color: gray; font-size: 11px;")
        ratio_note.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addLayout(lists_h)
        layout.addLayout(agg_h)
        layout.addLayout(stat_h)
        layout.addWidget(ratio_note)
        group.setLayout(layout)

        self.list_village.itemChanged.connect(
            lambda item: self._enforce_max(self.list_village, item))
        self.list_base.itemChanged.connect(
            lambda item: self._enforce_max(self.list_base, item))
        for lw in [self.list_village, self.list_base]:
            lw.itemChanged.connect(self._on_settings_changed)
        for cb in [self.cb_total, self.cb_village_agg, self.cb_base_agg,
                   *self.infra_stat_cbs.values()]:
            cb.stateChanged.connect(self._on_settings_changed)
        return group

    def _make_list(self) -> QListWidget:
        lw = QListWidget()
        lw.setSelectionMode(QAbstractItemView.NoSelection)
        lw.setMinimumHeight(180)
        return lw

    def _wrap(self, title: str, w: QWidget) -> QGroupBox:
        g = QGroupBox(title)
        lay = QVBoxLayout()
        lay.addWidget(w)
        g.setLayout(lay)
        return g

    def _enforce_max(self, lw: QListWidget, item: QListWidgetItem) -> None:
        checked = [lw.item(i) for i in range(lw.count())
                   if lw.item(i).checkState() == Qt.Checked]
        if len(checked) > 10 and item.checkState() == Qt.Checked:
            lw.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            lw.blockSignals(False)

    # ------------------------------------------------------------------ #
    # 레이어 변경 (Dialog에서 호출)                                         #
    # ------------------------------------------------------------------ #

    _DEFAULT_GEOJEOM_FIELDS = {
        "res_pop": "pop_r",
        "wor_pop": "pop_w",
        "inflow":  "pc_in",
        "outflow": "pc_out",
    }
    _DEFAULT_VILLAGE_COLS = {
        "kg_ox", "el_ox", "sl_ox", "ns_ox", "cc_ox",
        "sf_ox", "cli_ox", "ph_ox", "spark_ox", "bus_ox",
    }
    _DEFAULT_BASE_COLS = {
        "ps_ox", "pl_ox", "sw_ox", "slw_ox", "hmo_ox",
        "eg_ox", "pcf_ox", "tp_ox", "poli_ox", "fire_ox",
    }

    def update_geojeom_layer(self, layer: QgsVectorLayer) -> None:
        rows = [self.row_res_pop, self.row_wor_pop, self.row_inflow, self.row_outflow]
        for row in rows:
            row.set_layer(layer)

        # 기본 필드 자동 선택
        if layer:
            field_names = {f.name() for f in layer.fields()}
            defaults = [
                (self.row_res_pop, self._DEFAULT_GEOJEOM_FIELDS["res_pop"]),
                (self.row_wor_pop, self._DEFAULT_GEOJEOM_FIELDS["wor_pop"]),
                (self.row_inflow,  self._DEFAULT_GEOJEOM_FIELDS["inflow"]),
                (self.row_outflow, self._DEFAULT_GEOJEOM_FIELDS["outflow"]),
            ]
            for row, field_name in defaults:
                if field_name in field_names:
                    row.combo.setField(field_name)

    def update_infra_layer(self, layer: QgsVectorLayer) -> None:
        config_pairs = [
            (self.list_village, self._DEFAULT_VILLAGE_COLS),
            (self.list_base,    self._DEFAULT_BASE_COLS),
        ]
        for lw, defaults in config_pairs:
            lw.blockSignals(True)
            lw.clear()
            if layer:
                for f in layer.fields():
                    item = QListWidgetItem(f.name())
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    state = Qt.Checked if f.name() in defaults else Qt.Unchecked
                    item.setCheckState(state)
                    lw.addItem(item)
            lw.blockSignals(False)

    # ------------------------------------------------------------------ #
    # 분석 실행                                                            #
    # ------------------------------------------------------------------ #

    def _on_browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "결과 GeoPackage 저장", "", "GeoPackage (*.gpkg)"
        )
        if path:
            if not path.endswith(".gpkg"):
                path += ".gpkg"
            self.edit_output.setText(path)

    def _on_analyze(self) -> None:
        output_path = self.edit_output.text().strip()
        if not output_path:
            QMessageBox.warning(self, "경고", "출력 파일 경로를 지정하세요.")
            return
        if not self.is_valid():
            QMessageBox.warning(self, "경고", "필드를 모두 선택하고 통계를 최소 1개 이상 선택하세요.")
            return

        self._sync_to_config()
        self.config.output_path = output_path

        self._worker = AnalysisWorker(self.config)
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.task_completed.connect(self._on_finished)

        self.btn_analyze.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.log_widget.clear()
        self.log_widget.show()

        QgsApplication.taskManager().addTask(self._worker)

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress_bar.setValue(pct)
        self.log_widget.appendPlainText(f"[{pct:3d}%] {msg}")

    def _on_finished(self, success: bool, message: str) -> None:
        self.btn_analyze.setEnabled(True)
        self.log_widget.appendPlainText(message)
        if success:
            # 국토공간거점지도를 지도에 추가 (스트로크 없음)
            if self.config.geojeom_layer_path:
                try:
                    from ..renderer import add_geojeom_layer
                    add_geojeom_layer(self.config.geojeom_layer_path)
                except Exception:
                    pass

            QMessageBox.information(
                self, "완료",
                f"통계 분석이 완료되었습니다.\n"
                f"이제 Tab 3에서 분류 기준을 설정하고 분류를 실행하세요.\n\n"
                f"{self.config.output_path}"
            )
            self.analysis_done.emit()
        else:
            QMessageBox.critical(self, "오류", message)

    # ------------------------------------------------------------------ #
    # Config 동기화 / 유효성                                               #
    # ------------------------------------------------------------------ #

    def _on_settings_changed(self, *_) -> None:
        self._sync_to_config()
        self.settings_changed.emit()

    def _sync_to_config(self) -> None:
        gcfg = self.config.geojeom_cfg
        gcfg.field_resident_pop = self.row_res_pop.current_field()
        gcfg.field_work_pop     = self.row_wor_pop.current_field()
        gcfg.field_inflow       = self.row_inflow.current_field()
        gcfg.field_outflow      = self.row_outflow.current_field()
        gcfg.res_pop_stats  = self.row_res_pop.selected_stats()
        gcfg.wor_pop_stats  = self.row_wor_pop.selected_stats()
        gcfg.inflow_stats   = self.row_inflow.selected_stats()
        gcfg.outflow_stats  = self.row_outflow.selected_stats()

        icfg = self.config.infra_cfg
        icfg.village_cols = [
            self.list_village.item(i).text()
            for i in range(self.list_village.count())
            if self.list_village.item(i).checkState() == Qt.Checked
        ]
        icfg.base_cols = [
            self.list_base.item(i).text()
            for i in range(self.list_base.count())
            if self.list_base.item(i).checkState() == Qt.Checked
        ]
        icfg.compute_total   = self.cb_total.isChecked()
        icfg.compute_village = self.cb_village_agg.isChecked()
        icfg.compute_base    = self.cb_base_agg.isChecked()
        icfg.stats = [ist for ist, cb in self.infra_stat_cbs.items() if cb.isChecked()]

    def is_valid(self) -> bool:
        gcfg = self.config.geojeom_cfg
        return all([
            gcfg.field_resident_pop, gcfg.field_work_pop,
            gcfg.field_inflow, gcfg.field_outflow,
            gcfg.res_pop_stats, gcfg.wor_pop_stats,
            gcfg.inflow_stats, gcfg.outflow_stats,
        ])
