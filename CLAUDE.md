# cnt_classifier — 중심지 위계 설정 QGIS 플러그인

## 프로젝트 개요

중심지 폴리곤을 공간 분석을 통해 위계별로 분류하는 QGIS 플러그인이다. 두 격자 데이터셋과의 공간 교차 분석을 수행하여 중심지를 4단계 위계로 분류한다.

**위계 분류:**
- **광역중심지** — 최상위 (조건 1 + 조건 2 + 조건 3·4 AND 동시 충족)
- **지역중심지** — 중위 (조건 1 + 조건 2 충족)
- **생활중심지** — 기초 (조건 1만 충족)
- **이외** — 기준 미달

## 배포 방법

소스 디렉터리와 QGIS 플러그인 폴더를 수동으로 동기화한다. `.claude/settings.local.json`에 허가된 파일 복사 경로가 정의되어 있다.

- **소스**: `c:\Users\SEC\claude\cnt_classifier\`
- **QGIS 플러그인 폴더**: `C:\Users\SEC\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\cnt_classifier\`

파일 수정 후 QGIS에서 확인하려면 플러그인 폴더로 복사하고 QGIS를 재시작하거나 플러그인을 재로드해야 한다.

## 디렉터리 구조

```
cnt_classifier/
├── __init__.py         # QGIS 진입점 (classFactory)
├── plugin.py           # 플러그인 클래스 — 메뉴/툴바 등록
├── dialog.py           # 3탭 메인 다이얼로그
├── classifier.py       # 분류 엔진 (ConditionEvaluator)
├── processor.py        # 공간 분석 핵심 처리기
├── models.py           # 데이터 모델 & 설정 dataclass
├── utils.py            # 통계 계산 유틸리티
├── renderer.py         # 레이어 스타일링 및 지도 렌더링
├── worker.py           # QgsTask 기반 비동기 워커
├── metadata.txt        # QGIS 플러그인 메타데이터
└── ui/
    ├── tab_input.py    # Tab 1: 입력 파일 선택
    ├── tab_analysis.py # Tab 2: 분석 설정 및 실행
    └── tab_classify.py # Tab 3: 분류 기준 설정 및 실행
```

## 기술 스택

- **Python 3.x** + **PyQt5** (GUI)
- **QGIS >= 3.16** API (`qgis.core`, `qgis.gui`)
- 출력 포맷: **GeoPackage**

## 실행 흐름

1. **Tab 1** — 입력 레이어 3개 선택 (중심지, 국토공간거점지도, 생활인프라충족도)
2. **Tab 2 / Phase 1** — 공간 분석 실행 → 중심지별 인구·중심성·인프라 통계를 GeoPackage로 출력
3. **Tab 3 / Phase 2** — 분류 기준 적용 → "분류" 필드에 위계 결과 저장
   - 선택사항: 읍면동 단위 중복 제거 (주거 인구 최고인 폴리곤만 유지)
   - 선택사항: "이외" 분류 제거

## 핵심 파일 설명

### processor.py
공간 분석의 핵심. `QgsSpatialIndex`로 격자 셀 내 폴리곤 교차 조회 후 통계 계산.

- `execute()` — Phase 1: 3개 레이어 로드 → 격자 중심점 포함 여부 확인 → 통계 계산 → GeoPackage 저장
- `execute_dedup()` — Phase 1.5: 읍면동별 중복 제거
- `execute_phase2()` — Phase 2: 기존 GeoPackage에 분류 결과 추가
- `execute_delete_outside()` — "이외" 분류 피처 삭제

### classifier.py
`ConditionEvaluator` — 설정된 임계값과 연산자로 각 피처의 분류 결정.

### models.py
분석 전체 설정을 담는 dataclass들:
- `GeojeomConfig` — 국토공간거점지도 필드명 및 통계 종류
- `InfraConfig` — 생활인프라 컬럼 목록
- `ClassifyConfig` — 3단계 분류 조건 임계값
- `AnalysisConfig` — 마스터 설정 컨테이너

### worker.py
`QgsTask` 서브클래스로 Phase 1·2를 비동기 실행. UI 블로킹 방지.

## 입력 데이터

| 데이터 | 설명 | 주요 필드 |
|--------|------|-----------|
| 중심지 | 분류 대상 폴리곤 | (사용자 정의) |
| 국토공간거점지도 | 인구·중심성 격자 | `pop_r`, `pop_w`, `pc_in`, `pc_out` |
| 생활인프라충족도 (500m) | 시설 충족도 격자 | `kg_ox`, `el_ox`, ... (마을·기초 생활권) |

## 출력 데이터

GeoPackage 레이어명: `분류결과`

주요 출력 필드:
- `res_pop_*`, `wor_pop_*` — 인구 통계
- `inflow_*`, `outflow_*` — 중심성 통계
- `total_fac_*`, `vill_fac_*`, `base_fac_*` — 인프라 통계
- `분류` — 최종 위계 분류값

## 코드 작성 규칙

- UI 텍스트와 필드명은 **한국어** 사용
- 설정값은 `models.py`의 dataclass로 정의하고 UI → 로직으로 전달 (직접 하드코딩 금지)
- 무거운 처리는 반드시 `QgsTask` 워커로 비동기 실행
- 공간 쿼리에는 `QgsSpatialIndex` 사용 (브루트포스 순회 금지)
- 좌표계가 다른 레이어 간에는 `QgsCoordinateTransform`으로 변환 처리
