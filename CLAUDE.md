# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

국토공간거점지도 격자와 생활인프라충족도 격자를 공간 교차 분석하여 중심지 후보 폴리곤을 3단계 위계로 분류하는 QGIS 플러그인이다.

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
    "processor.py", "classifier.py", "models.py", "utils.py",
    "plugin.py",
    "processing\provider.py",
    "processing\alg_extract_candidates.py",
    "processing\alg_extract.py",
    "processing\alg_classify.py"
) | ForEach-Object { Copy-Item "$SRC\$_" "$DEST\$_" -Force }
```

테스트/린트 도구 없음 — QGIS Python 콘솔 또는 플러그인 재로드 후 직접 실행하여 검증한다.

## 실행 경로: Processing 알고리즘 전용

대화형 다이얼로그(`dialog.py`, `worker.py`, `ui/`)는 제거됨. 모든 기능은 **공간처리 툴박스**를 통해 실행한다.

`plugin.py`는 최상위 메뉴 `"KRIHS 공간구조 분석/시뮬레이션"`과 툴바를 등록하며, 메뉴/툴바의 3개 항목은 각 Processing 알고리즘 다이얼로그를 직접 호출(`processing.execAlgorithmDialog`)한다. Processing 프로바이더 ID: `krihs_cnt_classifier`.

### Processing 도구 순서

| 알고리즘 파일 | 도구명 | 핵심 동작 |
| --- | --- | --- |
| `alg_extract_candidates.py` | 중심지 후보 추출 | 격자에서 후보 폴리곤 생성 (독립 로직) |
| `alg_extract.py` | 중심지 후보 속성 추출 | `SpatialProcessor.execute()` 래핑, 완료 후 결과 레이어("중심지 후보 속성 추가") 지도 뷰 자동 추가 |
| `alg_classify.py` | 중심지 및 위계 설정 | QGIS 표현식 기반 cascade 분류, 입력 레이어 무수정, 새 레이어 출력 |

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

## Tab2 자동 필드 인식

`Tab2AnalysisWidget`은 레이어를 불러올 때 아래 기본값으로 자동 선택한다 (대화형 경로 제거 후 레거시이나 필드명 참조용):

- 거주인구: `pop_r`, 근무인구: `pop_w`, 유입: `pc_in`, 유출: `pc_out`
- 마을시설 기본 열: `kg_ox`, `el_ox`, `sl_ox`, `ns_ox`, `cc_ox`, `sf_ox`, `cli_ox`, `ph_ox`, `spark_ox`, `bus_ox`
- 거점시설 기본 열: `ps_ox`, `pl_ox`, `sw_ox`, `slw_ox`, `hmo_ox`, `eg_ox`, `pcf_ox`, `tp_ox`, `poli_ox`, `fire_ox`

## 코드 작성 규칙

- UI 텍스트와 필드명은 **한국어** 사용
- 설정값은 `models.py`의 dataclass로 정의하고 UI → 로직으로 전달 (직접 하드코딩 금지)
- 무거운 처리는 `processAlgorithm()` 내 동기 실행 (Processing 경로)
- 공간 쿼리에는 `QgsSpatialIndex` 사용 (브루트포스 순회 금지)
- 좌표계가 다른 레이어 간에는 `QgsCoordinateTransform`으로 변환 처리
- Processing 알고리즘은 `processor.py`의 기존 메서드를 재사용하고 별도 로직을 중복 구현하지 않는다
