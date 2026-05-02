import csv
import os
import urllib.parse
from collections import defaultdict

from PyQt5.QtCore import QVariant

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFileDestination,
    QgsProcessing,
    QgsProcessingException,
    QgsProcessingUtils,
    QgsSpatialIndex,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsFeature,
    QgsFeatureSink,
    QgsFields,
    QgsField,
    QgsWkbTypes,
    QgsProject,
    QgsVectorLayer,
)

from ..utils import safe_float

_UPPER_ID_FIELD = "상위중심지ID"


class AttractivenessUpperZoneAlgorithm(QgsProcessingAlgorithm):

    UPPER_LAYER      = "UPPER_LAYER"
    UPPER_TYPE_FIELD = "UPPER_TYPE_FIELD"
    UPPER_TYPES      = "UPPER_TYPES"
    UPPER_ID_FIELD   = "UPPER_ID_FIELD"

    SUB_LAYER        = "SUB_LAYER"
    SUB_ZONE_ID_FIELD = "SUB_ZONE_ID_FIELD"
    SUB_GRID_ID_FIELD = "SUB_GRID_ID_FIELD"

    CSV_LAYER      = "CSV_LAYER"
    CSV_FROM_FIELD = "CSV_FROM_FIELD"
    CSV_TO_FIELD   = "CSV_TO_FIELD"
    CSV_TRIP_FIELD = "CSV_TRIP_FIELD"

    DIST_LAYER      = "DIST_LAYER"
    DIST_FROM_FIELD = "DIST_FROM_FIELD"
    DIST_TO_FIELD   = "DIST_TO_FIELD"
    DIST_VALUE_FIELD = "DIST_VALUE_FIELD"
    DIST_UNIT       = "DIST_UNIT"

    OUTPUT_DISSOLVE     = "OUTPUT_DISSOLVE"
    OUTPUT_GRID         = "OUTPUT_GRID"
    OUTPUT_SCORE_CSV    = "OUTPUT_SCORE_CSV"
    OUTPUT_MOBILITY_CSV = "OUTPUT_MOBILITY_CSV"

    _CENTER_TYPES = ["생활중심지", "지역중심지", "광역중심지"]
    _DIST_UNITS   = ["미터 (m)", "킬로미터 (km)"]

    def name(self) -> str:
        return "attractiveness_upper_zone"

    def displayName(self) -> str:
        return "매력도 기반 상위생활권 도출"

    def group(self) -> str:
        return "중심지 분석"

    def groupId(self) -> str:
        return "center_analysis"

    def createInstance(self):
        return AttractivenessUpperZoneAlgorithm()

    def initAlgorithm(self, config=None) -> None:
        # ── 상위중심지 폴리곤 레이어 ─────────────────────────────────────
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.UPPER_LAYER, "상위중심지 폴리곤 레이어",
            types=[QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.UPPER_TYPE_FIELD, "중심지 유형 필드",
            parentLayerParameterName=self.UPPER_LAYER,
            type=QgsProcessingParameterField.String,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.UPPER_TYPES, "상위중심지 유형",
            options=self._CENTER_TYPES,
            allowMultiple=True,
            defaultValue=[2],  # 광역중심지
        ))
        self.addParameter(QgsProcessingParameterField(
            self.UPPER_ID_FIELD, "상위중심지 ID 필드",
            parentLayerParameterName=self.UPPER_LAYER,
        ))

        # ── 하위생활권(격자) 레이어 ──────────────────────────────────────
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.SUB_LAYER, "하위생활권(격자) 레이어",
            types=[QgsProcessing.TypeVectorPolygon],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SUB_ZONE_ID_FIELD, "생활권(중심지) ID 필드",
            parentLayerParameterName=self.SUB_LAYER,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.SUB_GRID_ID_FIELD, "격자 ID 필드",
            parentLayerParameterName=self.SUB_LAYER,
        ))

        # ── 모바일 통행 행렬 ─────────────────────────────────────────────
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.CSV_LAYER, "1km격자 모바일 통행 행렬 레이어 (CSV를 레이어로 추가)",
            types=[],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.CSV_FROM_FIELD, "From-ID 필드",
            parentLayerParameterName=self.CSV_LAYER,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.CSV_TO_FIELD, "To-ID 필드",
            parentLayerParameterName=self.CSV_LAYER,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.CSV_TRIP_FIELD, "통행량 필드",
            parentLayerParameterName=self.CSV_LAYER,
        ))

        # ── 중심지-중심지 간 거리 행렬 ──────────────────────────────────
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.DIST_LAYER, "중심지-중심지 간 거리 행렬 레이어",
            types=[],
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DIST_FROM_FIELD, "From-ID 필드",
            parentLayerParameterName=self.DIST_LAYER,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DIST_TO_FIELD, "To-ID 필드",
            parentLayerParameterName=self.DIST_LAYER,
        ))
        self.addParameter(QgsProcessingParameterField(
            self.DIST_VALUE_FIELD, "거리 필드",
            parentLayerParameterName=self.DIST_LAYER,
        ))
        self.addParameter(QgsProcessingParameterEnum(
            self.DIST_UNIT, "거리 단위",
            options=self._DIST_UNITS,
            defaultValue=0,  # 미터
        ))

        # ── 출력 ─────────────────────────────────────────────────────────
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_DISSOLVE, "상위생활권 권역 레이어",
            type=QgsProcessing.TypeVectorPolygon,
        ))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_GRID, "상위중심지 ID 할당 격자 레이어",
            type=QgsProcessing.TypeVectorPolygon,
        ))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_SCORE_CSV, "매력도 점수 CSV",
            fileFilter="CSV 파일 (*.csv)",
        ))
        mobility_csv_param = QgsProcessingParameterFileDestination(
            self.OUTPUT_MOBILITY_CSV, "이동량 행렬 CSV (선택)",
            fileFilter="CSV 파일 (*.csv)",
            optional=True,
            createByDefault=False,
        )
        self.addParameter(mobility_csv_param)

    def processAlgorithm(self, parameters, context, feedback):
        upper_layer    = self.parameterAsVectorLayer(parameters, self.UPPER_LAYER, context)
        upper_type_fld = self.parameterAsString(parameters, self.UPPER_TYPE_FIELD, context)
        upper_types    = {
            self._CENTER_TYPES[i]
            for i in self.parameterAsEnums(parameters, self.UPPER_TYPES, context)
        }
        upper_id_fld   = self.parameterAsString(parameters, self.UPPER_ID_FIELD, context)

        sub_layer     = self.parameterAsVectorLayer(parameters, self.SUB_LAYER, context)
        sub_zone_fld  = self.parameterAsString(parameters, self.SUB_ZONE_ID_FIELD, context)
        sub_grid_fld  = self.parameterAsString(parameters, self.SUB_GRID_ID_FIELD, context)

        csv_layer     = self.parameterAsVectorLayer(parameters, self.CSV_LAYER, context)
        csv_from      = self.parameterAsString(parameters, self.CSV_FROM_FIELD, context)
        csv_to        = self.parameterAsString(parameters, self.CSV_TO_FIELD, context)
        csv_trip      = self.parameterAsString(parameters, self.CSV_TRIP_FIELD, context)
        csv_path      = self._extract_csv_path(csv_layer)

        dist_layer     = self.parameterAsVectorLayer(parameters, self.DIST_LAYER, context)
        dist_from_fld  = self.parameterAsString(parameters, self.DIST_FROM_FIELD, context)
        dist_to_fld    = self.parameterAsString(parameters, self.DIST_TO_FIELD, context)
        dist_value_fld = self.parameterAsString(parameters, self.DIST_VALUE_FIELD, context)
        dist_in_meters = (self.parameterAsEnum(parameters, self.DIST_UNIT, context) == 0)

        score_csv_path    = self.parameterAsFileOutput(parameters, self.OUTPUT_SCORE_CSV, context)
        mobility_csv_path = self.parameterAsFileOutput(parameters, self.OUTPUT_MOBILITY_CSV, context)

        # ── Step 1. 하위생활권 격자 인덱스 구축 ─────────────────────────
        feedback.pushInfo("하위생활권 격자 인덱스 구축 중...")
        sub_index  = QgsSpatialIndex(sub_layer.getFeatures())
        sub_by_fid = {f.id(): f for f in sub_layer.getFeatures()}
        grid_to_zone = {}
        for f in sub_layer.getFeatures():
            grid_to_zone[str(f[sub_grid_fld])] = str(f[sub_zone_fld])
        feedback.pushInfo(f"  격자 수: {len(grid_to_zone):,}")

        # ── Step 2. 상위중심지별 포함 격자 추출 (centroid-in-polygon) ────
        feedback.pushInfo("상위중심지 공간 교차 분석 중...")
        transform = None
        if upper_layer.crs() != sub_layer.crs():
            transform = QgsCoordinateTransform(
                upper_layer.crs(), sub_layer.crs(), QgsProject.instance()
            )

        upper_center_grids = {}  # upper_id → set(grid_id)
        upper_center_ids   = set()

        for uf in upper_layer.getFeatures():
            if feedback.isCanceled():
                return {}
            if str(uf[upper_type_fld]) not in upper_types:
                continue

            upper_id   = str(uf[upper_id_fld])
            upper_geom = uf.geometry()
            if transform:
                upper_geom = QgsGeometry(upper_geom)
                upper_geom.transform(transform)

            grid_ids = set()
            for fid in sub_index.intersects(upper_geom.boundingBox()):
                sf = sub_by_fid.get(fid)
                if sf and upper_geom.contains(sf.geometry().centroid()):
                    grid_ids.add(str(sf[sub_grid_fld]))

            if grid_ids:
                upper_center_grids.setdefault(upper_id, set()).update(grid_ids)
                upper_center_ids.add(upper_id)

        grid_to_upper = {}  # grid_id → set(upper_id)
        for uid, gids in upper_center_grids.items():
            for gid in gids:
                grid_to_upper.setdefault(gid, set()).add(uid)

        feedback.pushInfo(f"  상위중심지 {len(upper_center_ids)}개, 포함 격자 추출 완료")

        if not upper_center_ids:
            raise QgsProcessingException(
                "선택한 유형에 해당하는 상위중심지가 없거나 교차 격자를 찾지 못했습니다."
            )

        # ── Step 3. CSV 단일 패스, 양방향 집계 ──────────────────────────
        feedback.pushInfo(f"모바일 통행 행렬 CSV 집계 중 (양방향): {csv_path}")
        file_obj    = self._open_csv(csv_path)
        mobility    = {}  # (zone_id, upper_id) → [inflow, outflow]
        row_count   = 0
        matched_fwd = matched_rev = 0

        try:
            reader = csv.DictReader(file_obj)
            for row in reader:
                if feedback.isCanceled():
                    break
                row_count += 1
                if row_count % 500_000 == 0:
                    feedback.pushInfo(f"  처리 행: {row_count:,}")

                from_id = str(row[csv_from])
                to_id   = str(row[csv_to])
                if from_id == to_id:
                    continue

                try:
                    trip = float(row[csv_trip])
                except (ValueError, TypeError):
                    continue

                # 방향 1: 하위생활권 격자 → 상위중심지 격자
                zone_id   = grid_to_zone.get(from_id)
                upper_ids = grid_to_upper.get(to_id)
                if zone_id is not None and upper_ids:
                    for uid in upper_ids:
                        mobility.setdefault((zone_id, uid), [0.0, 0.0])[0] += trip
                    matched_fwd += 1

                # 방향 2: 상위중심지 격자 → 하위생활권 격자
                upper_ids_from = grid_to_upper.get(from_id)
                zone_id_to     = grid_to_zone.get(to_id)
                if upper_ids_from and zone_id_to is not None:
                    for uid in upper_ids_from:
                        mobility.setdefault((zone_id_to, uid), [0.0, 0.0])[1] += trip
                    matched_rev += 1
        finally:
            file_obj.close()

        feedback.pushInfo(
            f"  총 {row_count:,}행 / 하위→상위 {matched_fwd:,}행, 상위→하위 {matched_rev:,}행 매칭"
        )

        # ── Step 4. (선택) 이동량 행렬 CSV 저장 ─────────────────────────
        if mobility_csv_path:
            with open(mobility_csv_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["하위생활권ID", "상위중심지ID", "유입통행량", "유출통행량"])
                for (z, u), (inf, out) in sorted(mobility.items()):
                    w.writerow([z, u, inf, out])
            feedback.pushInfo(f"  이동량 행렬 CSV 저장: {mobility_csv_path}")

        # ── Step 5. 거리 행렬 로드 ──────────────────────────────────────
        feedback.pushInfo("거리 행렬 로드 중...")
        distances = {}
        for feat in dist_layer.getFeatures():
            if feedback.isCanceled():
                return {}
            raw = safe_float(feat[dist_value_fld])
            distances[(str(feat[dist_from_fld]), str(feat[dist_to_fld]))] = \
                raw / 1000.0 if dist_in_meters else raw

        unit_label = "m→km 변환 적용" if dist_in_meters else "km 그대로 사용"
        feedback.pushInfo(f"  거리 레코드 수: {len(distances)} ({unit_label})")

        # ── Step 6. 매력도 점수 산출 → zone_to_upper ────────────────────
        # zone_id 자체가 상위중심지이면 자기 ID를 직접 할당
        # 그 외: score = (inflow + outflow) / dist_km² 최대값
        feedback.pushInfo("매력도 점수 산출 중...")
        zone_uppers = defaultdict(list)
        for (z, u) in mobility:
            zone_uppers[z].append(u)

        zone_to_upper = {}
        score_rows    = []
        no_dist_count = 0
        self_assigned = 0

        for zone_id, upper_ids in zone_uppers.items():
            if zone_id in upper_center_ids:
                zone_to_upper[zone_id] = zone_id
                self_assigned += 1
                continue

            best_upper = None
            best_score = -1.0

            for upper_id in upper_ids:
                inflow, outflow = mobility[(zone_id, upper_id)]
                dist = distances.get((zone_id, upper_id))

                if dist is None or dist <= 0:
                    no_dist_count += 1
                    score = None
                else:
                    score = (inflow + outflow) / (dist ** 2)
                    if score > best_score:
                        best_score = score
                        best_upper = upper_id

                score_rows.append((zone_id, upper_id, inflow, outflow, dist, score))

            if best_upper is not None:
                zone_to_upper[zone_id] = best_upper

        if no_dist_count:
            feedback.pushWarning(
                f"  거리 미존재 또는 0인 쌍 {no_dist_count}개 — 해당 쌍은 매력도 계산에서 제외"
            )
        feedback.pushInfo(
            f"  상위중심지 할당: {len(zone_to_upper)}개 하위생활권 (자기할당 {self_assigned}개 포함)"
        )

        # ── Step 7. 매력도 점수 CSV 저장 ────────────────────────────────
        with open(score_csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["하위생활권ID", "상위중심지ID", "유입통행량", "유출통행량", "거리", "매력도점수"])
            for (z, u, inf, out, dist, score) in sorted(score_rows, key=lambda r: (r[0], r[1])):
                w.writerow([z, u, inf, out,
                             "" if dist is None else dist,
                             "" if score is None else score])

        # ── Step 8. 격자 출력 레이어 ────────────────────────────────────
        feedback.pushInfo("격자 레이어에 상위중심지ID 할당 중...")
        grid_fields  = QgsFields(sub_layer.fields())
        existing_idx = grid_fields.indexOf(_UPPER_ID_FIELD)
        if existing_idx < 0:
            grid_fields.append(QgsField(_UPPER_ID_FIELD, QVariant.String, len=100))

        (grid_sink, grid_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_GRID, context,
            grid_fields, sub_layer.wkbType(), sub_layer.crs(),
        )

        upper_geoms = defaultdict(list)
        total = sub_layer.featureCount() or 1

        for i, feat in enumerate(sub_layer.getFeatures()):
            if feedback.isCanceled():
                break
            feedback.setProgress(int(i / total * 75))

            zone_id  = str(feat[sub_zone_fld])
            assigned = zone_to_upper.get(zone_id)

            out_feat = QgsFeature(grid_fields)
            out_feat.setGeometry(feat.geometry())

            if existing_idx < 0:
                out_feat.setAttributes(feat.attributes() + [assigned])
            else:
                attrs = list(feat.attributes())
                attrs[existing_idx] = assigned
                out_feat.setAttributes(attrs)

            grid_sink.addFeature(out_feat, QgsFeatureSink.FastInsert)

            if assigned:
                upper_geoms[assigned].append(feat.geometry())

        # ── Step 9. 상위생활권 권역 Dissolve ────────────────────────────
        feedback.pushInfo("상위생활권 권역 합역 중...")
        dissolve_fields = QgsFields()
        dissolve_fields.append(QgsField(_UPPER_ID_FIELD, QVariant.String, len=100))
        dissolve_fields.append(QgsField("격자수", QVariant.Int))

        (dissolve_sink, dissolve_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_DISSOLVE, context,
            dissolve_fields, QgsWkbTypes.MultiPolygon, sub_layer.crs(),
        )

        n_upper = len(upper_geoms)
        for j, (upper_id, geoms) in enumerate(sorted(upper_geoms.items())):
            if feedback.isCanceled():
                break
            feedback.setProgress(75 + int(j / max(n_upper, 1) * 25))

            merged = QgsGeometry.unaryUnion(geoms)
            if merged is None or merged.isNull():
                continue

            d_feat = QgsFeature(dissolve_fields)
            d_feat.setGeometry(merged)
            d_feat.setAttributes([upper_id, len(geoms)])
            dissolve_sink.addFeature(d_feat, QgsFeatureSink.FastInsert)

        feedback.setProgress(100)
        feedback.pushInfo(
            f"권역 수: {n_upper}, 미할당 하위생활권: "
            f"{len(zone_uppers) - len(zone_to_upper)}개"
        )

        self._dissolve_dest_id  = dissolve_dest_id
        self._grid_dest_id      = grid_dest_id
        self._score_csv_path    = score_csv_path
        self._mobility_csv_path = mobility_csv_path

        return {
            self.OUTPUT_DISSOLVE:     dissolve_dest_id,
            self.OUTPUT_GRID:         grid_dest_id,
            self.OUTPUT_SCORE_CSV:    score_csv_path,
            self.OUTPUT_MOBILITY_CSV: mobility_csv_path or "",
        }

    def postProcessAlgorithm(self, context, feedback) -> dict:
        for dest_id, name in [
            (getattr(self, "_dissolve_dest_id", None), "상위생활권 권역"),
            (getattr(self, "_grid_dest_id", None),     "상위중심지 ID 할당 격자"),
        ]:
            if not dest_id:
                continue
            layer = QgsProcessingUtils.mapLayerFromString(dest_id, context)
            if layer and layer.isValid():
                QgsProject.instance().addMapLayer(layer)

        for path, lyr_name in [
            (getattr(self, "_score_csv_path", None),    "매력도 점수"),
            (getattr(self, "_mobility_csv_path", None), "이동량 행렬"),
        ]:
            if path:
                lyr = QgsVectorLayer(path, lyr_name, "ogr")
                if lyr and lyr.isValid():
                    QgsProject.instance().addMapLayer(lyr)

        return {}

    def _extract_csv_path(self, layer):
        """delimitedtext 레이어의 소스 URI에서 실제 파일 경로를 추출한다."""
        source = layer.source()
        path = source.split("?")[0]
        if path.lower().startswith("file:///"):
            path = urllib.parse.unquote(path[8:])
            if not os.path.isabs(path):
                path = "/" + path
        if not os.path.isfile(path):
            raise QgsProcessingException(
                f"CSV 파일 경로를 확인할 수 없습니다: {path}\n"
                f"(레이어 소스: {layer.source()})\n"
                "QGIS에서 CSV를 '구분자로 구분된 텍스트 레이어'로 추가한 뒤 선택하세요."
            )
        return path

    def _open_csv(self, path):
        """UTF-8-SIG → UTF-8 → CP949 순으로 인코딩을 시도해 파일 객체 반환."""
        for enc in ("utf-8-sig", "utf-8", "cp949"):
            try:
                f = open(path, "r", encoding=enc, newline="")
                f.readline()
                f.seek(0)
                return f
            except (UnicodeDecodeError, Exception):
                try:
                    f.close()
                except Exception:
                    pass
        raise QgsProcessingException(
            f"CSV 파일 인코딩을 읽을 수 없습니다 (UTF-8/CP949 시도 실패): {path}"
        )
