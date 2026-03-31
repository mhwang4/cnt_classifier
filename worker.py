from qgis.core import QgsTask
from PyQt5.QtCore import pyqtSignal

from .models import AnalysisConfig
from .processor import AnalysisCancelledError, SpatialProcessor


class AnalysisWorker(QgsTask):
    """Phase 1: 통계 산출 → GeoPackage 저장."""

    progress_updated = pyqtSignal(int, str)
    task_completed = pyqtSignal(bool, str)

    def __init__(self, config: AnalysisConfig) -> None:
        super().__init__("중심지 통계 분석", QgsTask.CanCancel)
        self.processor = SpatialProcessor(config)
        self.exception = None

    def run(self) -> bool:
        try:
            self.processor.execute(progress_callback=self._report)
            return True
        except AnalysisCancelledError:
            return False
        except Exception as e:
            self.exception = e
            return False

    def finished(self, result: bool) -> None:
        if result:
            self.task_completed.emit(True, "통계 분석이 완료되었습니다.")
        elif self.exception:
            self.task_completed.emit(False, str(self.exception))
        else:
            self.task_completed.emit(False, "취소되었습니다.")

    def cancel(self) -> None:
        self.processor.cancel_requested = True
        super().cancel()

    def _report(self, pct: int, msg: str) -> None:
        self.setProgress(pct)
        self.progress_updated.emit(pct, msg)


class ClassifyWorker(QgsTask):
    """(선택) 읍면동 중복 제거 → 분류 → '이외' 삭제."""

    progress_updated = pyqtSignal(int, str)
    task_completed = pyqtSignal(bool, str)

    def __init__(self, config: AnalysisConfig) -> None:
        super().__init__("중심지 분류 적용", QgsTask.CanCancel)
        self.processor = SpatialProcessor(config)
        self.config = config
        self.exception = None

    def run(self) -> bool:
        try:
            if self.config.emd_layer_path:
                # 0–30%: 읍면동 중복 제거
                def dedup_cb(pct, msg):
                    scaled = int(pct * 0.30)
                    self.setProgress(scaled)
                    self.progress_updated.emit(scaled, msg)

                self.processor.execute_dedup(progress_callback=dedup_cb)

                # 30–80%: 분류
                def phase2_cb(pct, msg):
                    scaled = 30 + int(pct * 0.50)
                    self.setProgress(scaled)
                    self.progress_updated.emit(scaled, msg)

                self.processor.execute_phase2(progress_callback=phase2_cb)
            else:
                # 0–80%: 분류
                def phase2_only_cb(pct, msg):
                    scaled = int(pct * 0.80)
                    self.setProgress(scaled)
                    self.progress_updated.emit(scaled, msg)

                self.processor.execute_phase2(progress_callback=phase2_only_cb)

            # 80–100%: '이외' 삭제
            def del_cb(pct, msg):
                scaled = 80 + int(pct * 0.20)
                self.setProgress(scaled)
                self.progress_updated.emit(scaled, msg)

            self.processor.execute_delete_outside(progress_callback=del_cb)
            return True
        except AnalysisCancelledError:
            return False
        except Exception as e:
            self.exception = e
            return False

    def finished(self, result: bool) -> None:
        if result:
            self.task_completed.emit(True, "분류가 완료되었습니다.")
        elif self.exception:
            self.task_completed.emit(False, str(self.exception))
        else:
            self.task_completed.emit(False, "취소되었습니다.")

    def cancel(self) -> None:
        self.processor.cancel_requested = True
        super().cancel()

    def _report(self, pct: int, msg: str) -> None:
        self.setProgress(pct)
        self.progress_updated.emit(pct, msg)
