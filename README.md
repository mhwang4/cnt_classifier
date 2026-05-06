# 중심지 위계 설정 QGIS 플러그인

국토공간거점지도 격자와 생활인프라충족도 격자를 공간 교차 분석하여 중심지 후보 폴리곤을 **생활중심지 → 지역중심지 → 광역중심지** 3단계 위계로 분류하는 QGIS 플러그인입니다.

---

## 요구사항

| 항목 | 버전 |
|------|------|
| QGIS | 3.16 이상 |
| QNEAT3 플러그인 | 최신 (도로 OD 행렬 도구 사용 시 필요) |

---

## 설치

1. 이 저장소를 클론합니다.
   ```powershell
   git clone https://github.com/mhwang4/cnt_classifier.git
   ```

2. 아래 PowerShell 스크립트로 QGIS 플러그인 폴더에 파일을 복사합니다.
   ```powershell
   $SRC  = "C:\path\to\cnt_classifier"
   $DEST = "C:\Users\<사용자명>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\cnt_classifier"

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
   > `$DEST` 폴더가 없으면 먼저 `New-Item -ItemType Directory -Path $DEST`로 생성합니다.

3. QGIS를 재시작하거나 **Plugin Reloader**로 플러그인을 재로드합니다.

4. 설치 확인: 상단 메뉴에 **"KRIHS 공간구조 분석/시뮬레이션"** 이 나타나면 정상입니다.

---

## 위계 분류 기준

분류는 cascade 구조로 평가됩니다. 상위 조건을 충족해야 다음 단계로 진행합니다.

| 위계 | 조건 |
|------|------|
| 생활중심지 | `total_fac_avg >= 4.0` |
| 지역중심지 | 생활중심지 충족 + `base_fac_avg >= 5.0` |
| 광역중심지 | 지역중심지 충족 + `res_pop_sum >= 50000` AND `wor_pop_sum >= 50000` |
| (제외) | 생활중심지 미충족 → 출력에서 제외 |

기준값은 **"중심지 및 위계 설정"** 도구에서 QGIS 표현식으로 자유롭게 수정할 수 있습니다.

---

## 사용 방법 — 워크플로우

모든 도구는 **공간처리 툴박스**(`krihs_cnt_classifier` 그룹) 또는 상단 메뉴에서 실행합니다.

```
① 중심지 후보 추출
        ↓
② 중심지 후보 속성 추출
        ↓
③ 중심지 및 위계 설정
        ↓
④ 인구가중 중심지 대표점 추출
        ↓
⑤ 중심지-중심지 거리(도로) 행렬 산출   (QNEAT3 필요)
        ↓
⑥ 하위생활권-상위중심지 이동량 행렬 산출
        ↓
⑦ 매력도 기반 상위생활권 도출
```

---

## 도구 설명

### ① 중심지 후보 추출 (`extract_candidates`)

국토공간거점지도 격자에서 중심지 후보 폴리곤을 생성합니다.

- **후보그룹1** — `type` 필드가 `중심지Ⅰ` 또는 `중심지Ⅱ`인 격자
- **후보그룹2** — 나머지 격자 중 거주인구밀도 임계값 이상이며 그룹1 결과의 1km 버퍼 밖에 위치한 격자
- 버퍼 → 디졸브 → 역버퍼 → 단일파트 분리 파이프라인으로 폴리곤을 정제합니다.
- 읍면동 레이어를 입력하면 교차 면적 최대 읍면동 이름을 자동 할당합니다.
- **출력:** 후보그룹1 레이어, 후보그룹2 레이어, 통합 레이어 (필드: `중심지후보id`, `중심지후보이름`, `구분`)

### ② 중심지 후보 속성 추출 (`extract_center_attributes`)

중심지 후보 폴리곤과 격자 데이터를 공간 교차 분석하여 인구·인프라 통계를 추출합니다.

- 격자 셀의 **중심점이 폴리곤 내부에 포함**되는지 기준으로 귀속을 판정합니다.
- **출력 필드 패턴:**
  - 인구: `res_pop_*`, `wor_pop_*`, `inflow_*`, `outflow_*`
  - 인프라: `total_fac_*`, `vill_fac_*`, `base_fac_*`
- **출력:** GeoPackage (`분류결과` 레이어)

### ③ 중심지 및 위계 설정 (`classify_centers`)

QGIS 표현식을 사용하여 중심지를 위계별로 분류합니다.

- 유형별로 이름·표현식·위계값을 직접 설정할 수 있습니다.
- 입력 레이어는 수정하지 않고 `분류` 필드가 추가된 새 레이어를 출력합니다.
- 분류 결과는 카테고리 심볼로 지도에 자동 표시됩니다.

### ④ 인구가중 중심지 대표점 추출 (`pop_weighted_centroid`)

각 중심지 폴리곤에 속하는 격자의 인구 가중 centroid를 대표점으로 산출합니다.

- **출력:** 포인트 레이어

### ⑤ 중심지-중심지 거리(도로) 행렬 산출 (`od_matrix_road_distance`)

QNEAT3의 `OdMatrixFromLayersAsLines`를 래핑하여 중심지 간 도로 네트워크 거리를 계산합니다.

- 기점/종점 중심지 유형을 다중 선택할 수 있습니다.
- 도로망 레이어에 `ONEWAY` 필드가 필요합니다.
- **출력:** OD 행렬 라인 레이어

### ⑥ 하위생활권-상위중심지 이동량 행렬 산출 (`mobility_matrix`)

1km격자 모바일 통행 행렬 CSV를 읽어 (하위생활권, 상위중심지) 쌍별 유입·유출 통행량을 집계합니다.

- CSV는 QGIS에서 구분자 텍스트 레이어로 추가하여 입력합니다.
- 인코딩 자동 감지 (UTF-8-SIG → UTF-8 → CP949).
- **출력 CSV 헤더:** `하위생활권ID, 상위중심지ID, 유입통행량, 유출통행량`

### ⑦ 매력도 기반 상위생활권 도출 (`attractiveness_upper_zone`)

이동량 집계 → 매력도 점수 계산 → 격자 할당 → 권역 Dissolve를 단일 도구로 통합합니다.

- 매력도 공식: `score = (유입 + 유출) / 거리(km)²`
- **출력:**
  - 상위생활권 권역 폴리곤 레이어
  - 상위중심지ID 할당 격자 레이어
  - 매력도 점수 CSV
  - 이동량 행렬 CSV (선택)

---

## 입력 데이터 기본 필드명

국토공간거점지도 격자 표준 필드명 기준입니다. 도구 실행 시 파라미터에서 변경 가능합니다.

| 항목 | 필드명 |
|------|--------|
| 거주인구 | `pop_r` |
| 근무인구 | `pop_w` |
| 유입인구 | `pc_in` |
| 유출인구 | `pc_out` |
| 마을시설 열 | `kg_ox`, `el_ox`, `sl_ox`, `ns_ox`, `cc_ox`, `sf_ox`, `cli_ox`, `ph_ox`, `spark_ox`, `bus_ox` |
| 거점시설 열 | `ps_ox`, `pl_ox`, `sw_ox`, `slw_ox`, `hmo_ox`, `eg_ox`, `pcf_ox`, `tp_ox`, `poli_ox`, `fire_ox` |

---

## 개발 참고

- 빌드/테스트 도구 없음 — 파일 복사 후 QGIS Plugin Reloader로 재로드하여 검증합니다.
- 개발 가이드는 [CLAUDE.md](CLAUDE.md)를 참조하세요.
