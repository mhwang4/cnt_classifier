from PyQt5.QtWidgets import QDialog, QTabWidget, QVBoxLayout

from .models import AnalysisConfig
from .utils import build_output_field_names
from .ui.tab_input import Tab1InputWidget
from .ui.tab_analysis import Tab2AnalysisWidget
from .ui.tab_classify import Tab3ClassifyWidget


class CenterClassifierDialog(QDialog):
    """중심지 위계 설정 메인 다이얼로그 (3탭)."""

    def __init__(self, iface, parent=None) -> None:
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("중심지 위계 설정")
        self.setMinimumSize(780, 660)

        self.config = AnalysisConfig()

        self.tab_widget = QTabWidget()
        self.tab1 = Tab1InputWidget(self.config, iface, self)
        self.tab2 = Tab2AnalysisWidget(self.config, self)
        self.tab3 = Tab3ClassifyWidget(self.config, iface, self)

        self.tab_widget.addTab(self.tab1, "1. 입력 파일")
        self.tab_widget.addTab(self.tab2, "2. 분석 설정")
        self.tab_widget.addTab(self.tab3, "3. 분류 및 실행")

        # Tab 2, 3 초기 비활성
        self.tab_widget.setTabEnabled(1, False)
        self.tab_widget.setTabEnabled(2, False)

        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

        # 시그널 연결
        self.tab1.layers_ready.connect(self._on_layers_ready)
        self.tab2.settings_changed.connect(self._on_settings_changed)
        self.tab2.analysis_done.connect(self._on_analysis_done)

    # ------------------------------------------------------------------ #

    def _on_layers_ready(self, ready: bool) -> None:
        self.tab_widget.setTabEnabled(1, ready)
        if ready:
            _, geojeom, infra = self.tab1.get_layers()
            self.tab2.update_geojeom_layer(geojeom)
            self.tab2.update_infra_layer(infra)
        else:
            self.tab_widget.setTabEnabled(2, False)

    def _on_settings_changed(self) -> None:
        """Tab 2 설정이 변경되면 Tab 3 필드 드롭다운을 갱신 (Tab 3 활성화는 분석 완료 후)."""
        if self.tab2.is_valid():
            field_names = build_output_field_names(self.config)
            self.tab3.populate_field_dropdowns(field_names)

    def _on_analysis_done(self) -> None:
        """Tab 2 분석 완료 → Tab 3 활성화 + 출력 경로 표시."""
        self.tab_widget.setTabEnabled(2, True)
        self.tab3.refresh_output_label()
        # 분석 완료 후 Tab 3으로 자동 이동
        self.tab_widget.setCurrentIndex(2)
