# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

국토공간거점지도 격자와 생활인프라충족도 격자를 공간 교차 분석하여 중심지 후보 폴리곤을 3단계 위계로 분류하는 QGIS 플러그인이다. QGIS 3.16+ 필요.

**위계 분류 (cascade 구조):**

- **생활중심지** — `total_fac_avg >= 4.0` 충족
- **지역중심지** — 생활중심지 조건 충족 + `base_fac_avg >= 5.0` 충족
- **광역중심지** — 지역중심지 조건 충족 + `res_pop_sum >= 50000 AND wor_pop_sum >= 50000` 충족
- **이외** — 생활 조건 미충족 → 출력에서 제외

## 배포

QGIS는 자체 Python 인터프리터를 사용하므로 pip 설치나 별도 빌드 단계가 없다. 파일 수정 후 아래 명령으로 플러그인 폴더에 복사하고 QGIS를 재시작하거나 플러그인 리로더로 재로드한다.

**PowerShell (권장 — bash `fc` 내장 명령과 혼동 방지):**

```powershell
$SRC  = "C:\Users\SEC\claude\cnt_classifier"
$DEST = "C:\Users\SEC\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\cnt_classifier"
@(
    "__init__.py",
    "processor.py", "classifier.py", "models.py", "utils.py",
    "plugin.py",
    "processing\provider.py",
    "processing\alg_extract_candidates.py",
    "processing\alg_extract.py",
    "processing\alg_classify.py",
    "processing\alg_weighted_centroid.py",
    "processing\alg_od_matrix_road.py",
    "processing\alg_mobility_matrix.py",
    "processing\alg_attractiveness_upper_zone.py"
) | ForEach-Object { Copy-Item "$SRC\$_" "$DEST\$_" -Force }
```

테스트/린트 도구 없음 — QGIS Python 콘솔 또는 플러그인 재로드 후 직접 실행하여 검증한다.

## 실행 경로: Processing 알고리즘 전용

모든 기능은 **공간처리 툴박스**를 통해 실행한다.

`plugin.py`는 최상위 메뉴 `"KRIHS 공간구조 분석/시뮬레이션"`과 툴바를 등록하며, 각 항목은 `processing.execAlgorithmDialog`로 Processing 알고리즘 다이얼로그를 직접 호출한다. Processing 프로바이더 ID: `krihs_cnt_classifier`.

### Processing 도구 순서

| 알고리즘 파일 | 알고리즘 ID | 도구명 | 핵심 동작 |
| --- | --- | --- | --- |
| `alg_extract_candidates.py` | `extract_candidates` | 중심지 후보 추출 | 격자에서 후보 폴리곤 생성 (독립 로직) |
| `alg_extract.py` | `extract_center_attributes` | 중심지 후보 속성 추출 | `SpatialProcessor.execute()` 래핑, 완료 후 결과 레이어("중심지 후보 속성 추가") 지도 뷰 자동 추가 |
| `alg_classify.py` | `classify_centers` | 중심지 및 위계 설정 | QGIS 표현식 기반 cascade 분류, 입력 레이어 무수정, 새 레이어 출력 |
| `alg_weighted_centroid.py` | `pop_weighted_centroid` | 인구가중 중심지 대표점 추출 | 국토공간거점지도 격자 인구 가중 centroid 계산, 포인트 레이어 출력 |
| `alg_od_matrix_road.py` | `od_matrix_road_distance` | 중심지-중심지 거리(도로) 행렬 산출 | QNEAT3 `OdMatrixFromLayersAsLines` 래핑, 기점/종점 유형 다중 선택 |
| `alg_mobility_matrix.py` | `mobility_matrix` | 하위생활권-상위중심지 이동량 행렬 산출 | 1km격자 모바일 통행 행렬 CSV → (생활권, 상위중심지) 쌍별 유입·유출 집계 |
| `alg_attractiveness_upper_zone.py` | `attractiveness_upper_zone` | 매력도 기반 상위생활권 도출 | 이동량 집계+매력도 점수 계산+격자 할당+권역 Dissolve 통합 실행 |

전체 알고리즘 ID 형식: `krihs_cnt_classifier:<알고리즘 ID>`

### 새 알고리즘 추가 방법

1. `processing/alg_<name>.py` 생성 — `QgsProcessingAlgorithm` 서브클래스, `name()` 반환값이 알고리즘 ID
2. `processing/provider.py`에 import 추가 후 `loadAlgorithms()`에 `self.addAlgorithm(MyAlgorithm())` 추가
3. `plugin.py`의 메뉴/툴바 등록 블록에 항목 추가 (필요 시)
4. 배포 목록에 파일 추가 후 복사

## 레거시 코드 (비활성)

아래 파일들은 이전의 대화형 다이얼로그 경로 구현체다. 현재 플러그인 실행 흐름에서 사용되지 않으며, **수정하거나 재활성화할 의도가 없으면 건드리지 않는다.**

- `dialog.py` — 3탭 대화형 메인 다이얼로그 (Tab1: 파일 입력, Tab2: 분석 설정, Tab3: 분류)
- `worker.py` — `QgsTask` 기반 비동기 Phase 1/Phase 2 워커
- `renderer.py` — 레이어 시각화 스타일링 유틸리티 (`CATEGORY_STYLES`, `load_and_style_layer()`)
- `ui/` — Tab 위젯 구현체 (tab_input.py, tab_analysis.py, tab_classify.py)
- `classifier.py` — `ConditionEvaluator` 클래스 (cascade 분류 로직). `alg_classify.py` 재작성으로 현재 미사용.
- `processor.py`의 `execute_dedup()`, `execute_phase2()`, `execute_delete_outside()` 메서드

## `alg_classify.py` — 중심지 및 위계 설정

이전의 `ClassifyConfig`/`ConditionEvaluator` 기반에서 **QGIS 표현식 파라미터 기반**으로 완전 재작성됨.

**파라미터 구조 (유형별 3 슬롯, 고정):**

- `TYPE_N_ENABLED` (Boolean) — 유형 활성화
- `TYPE_N_NAME` (String) — 유형 이름
- `TYPE_N_EXPR` (Expression) — QGIS 표현식 빌더 팝업 연결, `parentLayerParameterName=INPUT`
- `TYPE_N_RANK` (Integer) — 위계값 (낮을수록 하위)

**기본값:**

| 슬롯 | 이름 | 표현식 |
| --- | --- | --- |
| 유형 1 | 생활중심지 | `"total_fac_avg" >= 4.0` |
| 유형 2 | 지역중심지 | `"base_fac_avg" >= 5.0` |
| 유형 3 | 광역중심지 | `"res_pop_sum" >= 50000 AND "wor_pop_sum" >= 50000` |

**Cascade 평가**: 위계값 오름차순 정렬 후 순서대로 평가. 조건 통과 시 해당 유형명 할당 후 다음 유형 평가 계속. 조건 실패 시 즉시 중단. 유형 1 미충족 피처는 출력에서 제외.

**출력**: `QgsProcessingParameterFeatureSink` — 입력 레이어의 속성을 복사(기존 `분류` 필드 교체)하고 `분류` 필드를 추가한 새 레이어.

**표현식 컨텍스트**: 필드 참조가 동작하려면 아래처럼 구성해야 한다 (`layerScope` 단독으로는 불충분):

```python
ctx = QgsExpressionContext()
ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(input_layer))
ctx.setFields(input_layer.fields())
```

**`postProcessAlgorithm`**: `QgsCategorizedSymbolRenderer`로 심볼 적용 후 지도 뷰에 추가.

**카테고리 색상 (스트로크 없음 — `Qt.NoPen`):**

| 분류 | 색상코드 |
| --- | --- |
| 생활중심지 | `#33a02c` |
| 지역중심지 | `#ff7f00` |
| 광역중심지 | `#8c0000` |

## `alg_extract_candidates.py` — 중심지 후보 추출

두 그룹의 후보를 독립적으로 처리하고 통합 출력 레이어를 생성한다.

- **후보그룹1**: `type` 필드가 `"중심지Ⅰ"` 또는 `"중심지Ⅱ"`인 격자
- **후보그룹2**: 나머지 격자 중 거주인구밀도 임계값 이상이며 후보그룹1 결과물의 **1km 버퍼 밖**에 위치한 격자

**처리 파이프라인 (두 그룹 공통)**: 양의 버퍼(정사각형 끝, 마이터 이음새) → 디졸브 → 음의 버퍼 → 단일파트 분리 → 점 접촉 폴리곤 병합(옵션)

**읍면동 이름 할당**: **교차 면적 최대** 읍면동 이름을 할당하되, 끝글자가 `읍`·`면`·`동`이면 제거한다. 동일 읍면동 내 중복은 `_2`, `_3` suffix 추가. EMD 레이어 미설정 시 `중심지후보_N` 형식 사용.

**읍면동별 중복 제거 (`_dedup_by_emd`)**: EMD 귀속도 교차 면적 최대 방식으로 판정(이름 할당과 동일 기준). 버킷 키는 `emd_fid` 단독(그룹 구분 없음) — 그룹1·2 통합 기준으로 읍면동당 `res_pop_sum` 최대 폴리곤 1개 보존.

출력: 후보그룹1 레이어, 후보그룹2 레이어, 통합 레이어 3종. 통합 레이어 필드: `중심지후보id`, `중심지후보이름`, `구분`(값: `중심지후보그룹1` 또는 `중심지후보그룹2`).

## `alg_weighted_centroid.py` — 인구가중 중심지 대표점 추출

중심지 폴리곤 레이어와 국토공간거점지도(격자) 레이어를 입력받아 인구 가중 centroid 포인트를 산출한다.

**파라미터:**

- `INPUT` (Polygon) — 중심지 폴리곤 레이어
- `GEOJEOM_LAYER` (Polygon) — 국토공간거점지도 격자 레이어
- `POP_FIELD` (Numeric Field from GEOJEOM_LAYER) — 인구 필드
- `OUTPUT` (FeatureSink, Point) — 대표점 레이어

**계산 방식:** 각 중심지 폴리곤에 속하는 격자(centroid-in-polygon) 목록에서
`weighted_x += pop * cx`, `total_weight += pop` 누적 후 `wx = weighted_x / total_weight`.
`total_weight == 0`이면 폴리곤 centroid로 대체.

**CRS 처리:** GEOJEOM_LAYER CRS → INPUT CRS 변환(`to_geojeom`), 결과 포인트 역변환(`to_center`).

---

## `alg_od_matrix_road.py` — 중심지-중심지 거리(도로) 행렬 산출

QNEAT3 플러그인의 `OdMatrixFromLayersAsLines` 알고리즘을 래핑한다.

**파라미터:**

- `INPUT` (Point) — 중심지 대표점 레이어
- `NETWORK_LAYER` (Line) — 도로망 레이어 (KTDB GIS, UTM-K EPSG:5179 권장)
- `TYPE_FIELD` (String Field) — 중심지 유형 필드
- `FROM_TYPE` / `TO_TYPE` (Enum, allowMultiple) — 기점/종점 유형 (`_CENTER_TYPES` 목록)
- `FROM_ID_FIELD` / `TO_ID_FIELD` (Field) — 기점/종점 ID 필드

**주의:** 네트워크 레이어에 `ONEWAY` 필드가 없으면 실행 전 오류 발생.

**내부 동작:** `_make_filtered_layer()`로 유형별 임시 메모리 레이어 생성 후 QNEAT3 호출
(`STRATEGY=0`, `ENTRY_COST_CALCULATION_METHOD=1`, `DEFAULT_DIRECTION=2`).

**출력:** `QgsProcessingOutputVectorLayer` — `postProcessAlgorithm`에서 레이어명 "중심지-중심지 OD 행렬"로 지도 뷰 추가.

---

## `alg_mobility_matrix.py` — 하위생활권-상위중심지 이동량 행렬 산출

1km격자 모바일 통행 행렬 CSV를 스트리밍으로 읽어 (하위생활권ID, 상위중심지ID) 쌍별 유입·유출 통행량을 집계한다. 단독 실행용 도구로 유지되며, `alg_attractiveness_upper_zone.py`에도 동일 로직이 내장되어 있다.

**파라미터:**

- `SUB_LAYER` (Polygon) — 하위생활권(격자) 레이어
- `SUB_ZONE_ID_FIELD` — 생활권(중심지) ID 필드
- `SUB_GRID_ID_FIELD` — 격자 ID 필드
- `UPPER_LAYER` (Polygon) — 상위중심지 폴리곤 레이어
- `UPPER_TYPE_FIELD` / `UPPER_TYPES` / `UPPER_ID_FIELD` — 유형 필터 및 ID
- `CSV_LAYER` (any vector) — 통행 행렬 레이어 (CSV를 구분자 텍스트 레이어로 추가)
- `CSV_FROM_FIELD` / `CSV_TO_FIELD` / `CSV_TRIP_FIELD` — 컬럼 필드 선택
- `OUTPUT` (FileDestination CSV)

**핵심 구현:**

- `_extract_csv_path()`: `file:///` URI에서 실제 경로 추출
- `_open_csv()`: UTF-8-SIG → UTF-8 → CP949 인코딩 자동 감지
- 단일 패스 양방향 집계: 방향1(하위→상위) + 방향2(상위→하위) 동시 처리
- `from_id == to_id` 자기 이동 제외, 50만 행마다 진행 상황 출력

**출력 CSV 헤더:** `하위생활권ID, 상위중심지ID, 유입통행량, 유출통행량`

**`postProcessAlgorithm`:** 출력 CSV를 ogr 레이어로 지도 뷰에 추가.

---

## `alg_attractiveness_upper_zone.py` — 매력도 기반 상위생활권 도출

이동량 행렬 산출 + 매력도 점수 계산 + 격자 할당 + 권역 Dissolve를 단일 도구로 통합.
파라미터 31개(두 도구 합산) → 20개로 단순화.

**파라미터 4그룹:**

| 그룹 | 주요 파라미터 |
| --- | --- |
| 상위중심지 폴리곤 | `UPPER_LAYER`, `UPPER_TYPE_FIELD`, `UPPER_TYPES`(Enum 다중선택, 기본값: 광역중심지), `UPPER_ID_FIELD` |
| 하위생활권(격자) | `SUB_LAYER`, `SUB_ZONE_ID_FIELD`, `SUB_GRID_ID_FIELD` |
| 모바일 통행 행렬 | `CSV_LAYER`(any vector), `CSV_FROM_FIELD`, `CSV_TO_FIELD`, `CSV_TRIP_FIELD` |
| 거리 행렬 | `DIST_LAYER`, `DIST_FROM_FIELD`, `DIST_TO_FIELD`, `DIST_VALUE_FIELD`, `DIST_UNIT`(미터/km) |

**출력:**

- `OUTPUT_DISSOLVE` — 상위생활권 권역 폴리곤 레이어 (상위중심지ID, 격자수 필드)
- `OUTPUT_GRID` — 상위중심지ID 할당 격자 레이어
- `OUTPUT_SCORE_CSV` — 매력도 점수 CSV
- `OUTPUT_MOBILITY_CSV` — 이동량 행렬 CSV (**선택**, `optional=True`)

**핵심 로직 (단계별):**

1. 격자 공간 인덱스 구축 → `grid_to_zone`
2. centroid-in-polygon → `upper_center_grids`, `grid_to_upper`, `upper_center_ids`
3. CSV 단일 패스 양방향 집계 → `mobility {(zone_id, upper_id) → [inflow, outflow]}`
4. (선택) 이동량 CSV 저장
5. 거리 행렬 로드 (미터이면 /1000 변환)
6. 매력도 산출: `score = (inflow + outflow) / dist_km²`  
   — `zone_id ∈ upper_center_ids`이면 자기 ID 직접 할당 (매력도 계산 생략)
7. 매력도 점수 CSV 저장
8. 격자 출력 (`상위중심지ID` 필드 추가/갱신)
9. `QgsGeometry.unaryUnion` per upper_id → Dissolve 레이어

**CSV 처리 유틸 (`_extract_csv_path`, `_open_csv`):** `alg_mobility_matrix.py`와 동일 구현.

---

## `alg_extract.py` — 중심지 후보 속성 추출

`SpatialProcessor.execute()`를 래핑. 인프라 통계 기본값은 **평균(AVG) 단독**(`defaultValue=[0]`). 완료 후 GeoPackage 내 `분류결과` 레이어를 `"중심지 후보 속성 추가"` 이름으로 지도 뷰에 자동 추가.

## 핵심 파일: `processor.py` — `SpatialProcessor`

공간 분석의 중심. 현재 Processing 경로에서 `execute()`만 활성 사용됨.

**메서드:**

- `execute()` — 레이어 로드 → 공간 인덱스 구축 → 격자별 통계 계산 → GeoPackage 저장
- `execute_dedup()`, `execute_phase2()`, `execute_delete_outside()` — 대화형 다이얼로그 경로 제거로 현재 미사용 (레거시)

**공간 교차 방식**: `_get_intersecting()`은 격자 셀의 **중심점(centroid)이 중심지 폴리곤 내부에 포함**되는지 확인한다. 격자 셀은 하나의 중심지에만 귀속된다.

**레이어 로드 (`_load_layers`)**: `ogr` 프로바이더로 먼저 시도하고, 실패 시 `QgsProject.instance().mapLayers()`를 순회하여 `.source()`가 일치하는 레이어를 반환한다. 임시(메모리) 레이어도 입력으로 사용 가능.

**QGIS API 호환**: `_write_geopackage()`는 `QgsVectorFileWriter.create()`(3.20+) 먼저 시도, 실패 시 구버전 생성자로 폴백.

## `utils.py` — 유틸리티 함수

- `build_output_field_names(config)`: 출력 GeoPackage 스키마 단일 소스. 새 통계 필드 추가 시 이 함수, `processor.py` 통계 계산, `models.py`의 `StatType`/`InfraStatType`을 함께 수정.
- `compute_stats(values, stats, area) -> Dict[str, float]`: SUM/MAX/MIN/AVG/DENSITY 계산. DENSITY는 `sum / area_km2`.
- `compute_infra_stats(values, stats, n_cols) -> Dict[str, float]`: `_RATIO` 변종은 `value / n_cols`로 정규화.
- `safe_float(value) -> float`: 변환 실패 시 `0.0` 반환.

## 출력 필드명

출력 GeoPackage 레이어명: `분류결과`  
주요 출력 필드 패턴: `res_pop_*`, `wor_pop_*`, `inflow_*`, `outflow_*`, `total_fac_*`, `vill_fac_*`, `base_fac_*`, `분류`

## `models.py` — 설정 dataclass

| 클래스 | 역할 |
| --- | --- |
| `GeojeomConfig` | 국토공간거점지도 필드명 4개 + 통계 종류(`StatType` 리스트) |
| `InfraConfig` | 생활인프라 마을/거점 컬럼 목록 + 집계 항목 + 통계 종류(`InfraStatType` 리스트) |
| `ClassifyConfig` | 3단계 분류 조건 — `alg_classify.py` 재작성으로 현재 미사용 (레거시) |
| `AnalysisConfig` | 마스터 컨테이너 — 파일 경로 4개 + 위 config들 |

## 입력 레이어 기본 필드명 (참조용)

`alg_extract.py` 파라미터 기본값 기준 — 국토공간거점지도 격자 표준 필드명:

- 거주인구: `pop_r`, 근무인구: `pop_w`, 유입: `pc_in`, 유출: `pc_out`
- 마을시설 열: `kg_ox`, `el_ox`, `sl_ox`, `ns_ox`, `cc_ox`, `sf_ox`, `cli_ox`, `ph_ox`, `spark_ox`, `bus_ox`
- 거점시설 열: `ps_ox`, `pl_ox`, `sw_ox`, `slw_ox`, `hmo_ox`, `eg_ox`, `pcf_ox`, `tp_ox`, `poli_ox`, `fire_ox`

## QGIS API 패턴

### 표현식 컨텍스트 (alg_classify.py 방식)

필드 참조가 동작하려면 `layerScope` 단독으로는 불충분하다. 아래처럼 `setFields()`까지 호출해야 한다:

```python
ctx = QgsExpressionContext()
ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
ctx.setFields(layer.fields())  # 필수
```

### 피드백 패턴

```python
if feedback.isCanceled():
    return {}
feedback.setProgress(int(i / total * 100))
feedback.pushInfo("메시지")
```

### 공간 인덱스 + 중심점-in-폴리곤 패턴

```python
index = QgsSpatialIndex(layer.getFeatures())
feat_map = {f.id(): f for f in layer.getFeatures()}
# bbox 후보 조회 → containsPoint 정밀 검사
for fid in index.intersects(polygon.boundingBox()):
    grid = feat_map[fid]
    if polygon.contains(grid.geometry().centroid()):
        ...
```

### 파라미터 명명 규칙

| 용도 | 패턴 | 예시 |
| --- | --- | --- |
| 기본 입력 레이어 | `INPUT` | `INPUT` |
| 추가 레이어 | `<ROLE>_LAYER` | `GEOJEOM_LAYER` |
| 필드 선택 | `<ROLE>_FIELD` | `TYPE_FIELD`, `POP_FIELD` |
| Enum/다중선택 | `<ROLE>_TYPE(S)` | `FROM_TYPE`, `UPPER_TYPES` |
| 기본 출력 | `OUTPUT` | `OUTPUT` |
| 추가 출력 | `OUTPUT_<NAME>` | `OUTPUT_DISSOLVE`, `OUTPUT_GRID` |

## 코드 작성 규칙

- UI 텍스트와 필드명은 **한국어** 사용
- 설정값은 `models.py`의 dataclass로 정의하고 UI → 로직으로 전달 (직접 하드코딩 금지)
- 무거운 처리는 `processAlgorithm()` 내 동기 실행 (Processing 경로)
- 공간 쿼리에는 `QgsSpatialIndex` 사용 (브루트포스 순회 금지)
- 좌표계가 다른 레이어 간에는 `QgsCoordinateTransform`으로 변환 처리
- Processing 알고리즘은 `processor.py`의 기존 메서드를 재사용하고 별도 로직을 중복 구현하지 않는다
