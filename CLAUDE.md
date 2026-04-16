# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

국토공간거점지도 격자와 생활인프라충족도 격자를 공간 교차 분석하여 중심지 후보 폴리곤을 4단계 위계로 분류하는 QGIS 플러그인이다.

**위계 분류 (cascade 구조):**

- **광역중심지** — 지역중심지 조건 충족 + 광역 AND 조건(res_pop_sum, wor_pop_sum) 동시 충족
- **지역중심지** — 생활중심지 조건 충족 + 지역 조건(base_fac_avg_ratio) 충족
- **생활중심지** — 생활 조건(total_fac_avg_ratio) 충족
- **이외** — 생활 조건 미충족

## 배포

QGIS는 자체 Python 인터프리터를 사용하므로 pip 설치나 별도 빌드 단계가 없다. 파일 수정 후 아래 명령으로 플러그인 폴더에 복사하고 QGIS를 재시작하거나 플러그인 리로더로 재로드한다.

```bash
SRC="C:/Users/SEC/claude/cnt_classifier"
DEST="C:/Users/SEC/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/cnt_classifier"
cp "$SRC/processor.py"                       "$DEST/processor.py"
cp "$SRC/classifier.py"                      "$DEST/classifier.py"
cp "$SRC/models.py"                          "$DEST/models.py"
cp "$SRC/utils.py"                           "$DEST/utils.py"
cp "$SRC/worker.py"                          "$DEST/worker.py"
cp "$SRC/renderer.py"                        "$DEST/renderer.py"
cp "$SRC/dialog.py"                          "$DEST/dialog.py"
cp "$SRC/plugin.py"                          "$DEST/plugin.py"
cp "$SRC/ui/tab_input.py"                    "$DEST/ui/tab_input.py"
cp "$SRC/ui/tab_analysis.py"                 "$DEST/ui/tab_analysis.py"
cp "$SRC/ui/tab_classify.py"                 "$DEST/ui/tab_classify.py"
cp "$SRC/processing/provider.py"             "$DEST/processing/provider.py"
cp "$SRC/processing/alg_extract_candidates.py" "$DEST/processing/alg_extract_candidates.py"
cp "$SRC/processing/alg_extract.py"          "$DEST/processing/alg_extract.py"
cp "$SRC/processing/alg_classify.py"         "$DEST/processing/alg_classify.py"
```

테스트/린트 도구 없음 — QGIS Python 콘솔 또는 플러그인 재로드 후 직접 실행하여 검증한다.

## 두 가지 실행 경로

이 플러그인은 동일한 `SpatialProcessor` 로직을 두 가지 방식으로 실행한다.

### 1. 대화형 다이얼로그 경로 (`dialog.py` → `worker.py`)

```
CenterClassifierDialog (dialog.py)
  ├── Tab1InputWidget     → AnalysisConfig에 파일 경로 설정
  ├── Tab2AnalysisWidget  → GeojeomConfig, InfraConfig, output_path 설정
  │     └── AnalysisWorker (QgsTask) → SpatialProcessor.execute()
  └── Tab3ClassifyWidget  → ClassifyConfig, emd_layer_path, sgg_layer_path 설정
        └── ClassifyWorker (QgsTask) → execute_dedup()? → execute_phase2() → execute_delete_outside()
```

`dialog.py`가 단일 `AnalysisConfig()` 인스턴스를 생성해 세 탭 모두에 레퍼런스로 전달한다. 탭 활성화 순서:

1. Tab 2: Tab 1에서 레이어 3개가 모두 선택되어야 활성화
2. Tab 3: Tab 2 분석(`execute()`) 완료 후 활성화
3. Tab 2 설정 변경 시 `build_output_field_names(config)`를 호출해 Tab 3 필드 드롭다운을 즉시 갱신

**`ClassifyWorker`**: 읍면동 경로가 설정된 경우에만 `execute_dedup()`을 실행한다. `execute_delete_outside()`는 항상 실행된다(다이얼로그에는 '이외' 삭제 선택 옵션이 없음).

### 2. Processing 알고리즘 경로 (`processing/`)

Processing 도구 메뉴 순서: **후보 추출 → 속성 추출 → 위계 설정**

| 알고리즘 파일 | 도구명 | 핵심 동작 |
| --- | --- | --- |
| `alg_extract_candidates.py` | 중심지 후보 추출 | 격자에서 후보 폴리곤 생성 (독립 로직) |
| `alg_extract.py` | 중심지 후보 속성 추출 | `SpatialProcessor.execute()` 래핑, 완료 후 결과 레이어 지도 뷰 자동 추가 |
| `alg_classify.py` | 중심지 추출 및 위계 설정 | `execute_dedup()`? → `execute_phase2()` → `execute_delete_outside()` 래핑, `DELETE_OUTSIDE` 불리언 파라미터 있음 |

`alg_classify.py`는 입력 레이어 source에서 `|layername=분류결과`를 제거해 GeoPackage 파일 경로만 추출한다.

## 핵심 파일: `processor.py` — `SpatialProcessor`

공간 분석의 중심. 모든 무거운 처리가 여기에 있다.

**메서드 실행 순서:**

- `execute()` — 레이어 로드 → 공간 인덱스 구축 → 격자별 통계 계산 → GeoPackage 저장
- `execute_dedup()` — 읍면동 경계를 기준으로 같은 읍면동 내 중복 폴리곤 중 `res_pop_sum` 최대값 1개만 보존
- `execute_phase2()` — 기존 GeoPackage에 `분류` 필드 추가·업데이트 (`ConditionEvaluator` 사용)
- `execute_delete_outside()` — `분류 == "이외"` 피처 삭제, 삭제 수 반환

**공간 교차 방식**: `_get_intersecting()`은 격자 셀의 **중심점(centroid)이 중심지 폴리곤 내부에 포함**되는지 확인한다 (폴리곤 vs 폴리곤 교차가 아님). 격자 셀은 하나의 중심지에만 귀속된다.

**레이어 로드 (`_load_layers`)**: `ogr` 프로바이더로 먼저 시도하고, 실패 시 `QgsProject.instance().mapLayers()`를 순회하여 `.source()`가 일치하는 레이어를 반환한다. 이 폴백 덕분에 임시(메모리) 레이어를 Processing 알고리즘의 입력으로 사용할 수 있다.

**QGIS API 호환**: `_write_geopackage()`는 `QgsVectorFileWriter.create()`(3.20+)를 먼저 시도하고 실패하면 구버전 생성자로 폴백한다.

## 출력 필드명 단일 소스

`utils.build_output_field_names(config)` 가 출력 GeoPackage 스키마와 Tab 3 드롭다운 양쪽의 단일 소스다. 새 통계 필드를 추가할 때는 이 함수, `processor.py`의 통계 계산, `models.py`의 관련 `StatType`/`InfraStatType`을 모두 함께 수정해야 한다.

출력 GeoPackage 레이어명: `분류결과`  
주요 출력 필드 패턴: `res_pop_*`, `wor_pop_*`, `inflow_*`, `outflow_*`, `total_fac_*`, `vill_fac_*`, `base_fac_*`, `분류`

## `alg_extract_candidates.py` — 중심지 후보 추출

두 그룹의 후보를 독립적으로 처리하고 통합 출력 레이어를 생성한다.

- **후보그룹1**: `type` 필드가 `"중심지Ⅰ"` 또는 `"중심지Ⅱ"`인 격자
- **후보그룹2**: 나머지 격자 중 거주인구밀도 임계값 이상이며 후보그룹1 결과물의 **1km 버퍼 밖**에 위치한 격자

**처리 파이프라인 (두 그룹 공통)**: 양의 버퍼(정사각형 끝, 마이터 이음새) → 디졸브 → 음의 버퍼 → 단일파트 분리 → 점 접촉 폴리곤 병합(옵션)

**읍면동 이름 할당**: 교차 면적 최대 읍면동 이름을 할당하되, 끝글자가 `읍`·`면`·`동`이면 제거한다. 동일 읍면동 내 중복은 `_2`, `_3` 형식 suffix 추가. EMD 레이어 미설정 시 `중심지후보_N` 형식 사용.

출력: 후보그룹1 레이어, 후보그룹2 레이어, 통합 레이어 3종. 통합 레이어 필드: `중심지후보id`, `중심지후보이름`, `구분`(값: `중심지후보그룹1` 또는 `중심지후보그룹2`).

## `models.py` — 설정 dataclass

| 클래스 | 역할 |
| --- | --- |
| `GeojeomConfig` | 국토공간거점지도 필드명 4개 + 통계 종류(`StatType` 리스트) |
| `InfraConfig` | 생활인프라 마을/거점 컬럼 목록 + 집계 항목 + 통계 종류(`InfraStatType` 리스트) |
| `ClassifyConfig` | 3단계 분류 조건(필드명, `Operator`, 임계값) |
| `AnalysisConfig` | 마스터 컨테이너 — 파일 경로 4개 + 위 3개 config |

분류 조건 기본값: 생활(total_fac_avg_ratio ≥ 0.20), 지역(base_fac_avg_ratio ≥ 0.50), 광역(res_pop_sum ≥ 50000 AND wor_pop_sum ≥ 50000).

## `renderer.py`

분류 완료 후 레이어를 지도 뷰에 추가하는 함수들.

- `load_and_style_layer()`: `분류결과` 레이어 로드 + 4개 범주 심볼(`QgsCategorizedSymbolRenderer`) 적용 + 프로젝트 추가
- `add_emd_layer()`: 읍면동 경계, 채우기 없음, 회색 0.5px 경계선
- `add_sgg_layer()`: 시군구 경계, 채우기 없음, 짙은 회색 1.5px 경계선
- `add_geojeom_layer()`: 국토공간거점지도, 스트로크 없음

## Tab2 자동 필드 인식

`Tab2AnalysisWidget`은 레이어를 불러올 때 아래 기본값으로 자동 선택한다:

- 거주인구: `pop_r`, 근무인구: `pop_w`, 유입: `pc_in`, 유출: `pc_out`
- 마을시설 기본 열: `kg_ox`, `el_ox`, `sl_ox`, `ns_ox`, `cc_ox`, `sf_ox`, `cli_ox`, `ph_ox`, `spark_ox`, `bus_ox`
- 거점시설 기본 열: `ps_ox`, `pl_ox`, `sw_ox`, `slw_ox`, `hmo_ox`, `eg_ox`, `pcf_ox`, `tp_ox`, `poli_ox`, `fire_ox`

## 코드 작성 규칙

- UI 텍스트와 필드명은 **한국어** 사용
- 설정값은 `models.py`의 dataclass로 정의하고 UI → 로직으로 전달 (직접 하드코딩 금지)
- 무거운 처리는 반드시 `QgsTask` 워커로 비동기 실행 (다이얼로그 경로) 또는 `processAlgorithm()` 내 동기 실행 (Processing 경로)
- 공간 쿼리에는 `QgsSpatialIndex` 사용 (브루트포스 순회 금지)
- 좌표계가 다른 레이어 간에는 `QgsCoordinateTransform`으로 변환 처리
- Processing 알고리즘은 `processor.py`의 기존 메서드를 재사용하고 별도 로직을 중복 구현하지 않는다
