# 룰렛 프로젝트 help.md (리셋본)

## 문서 리셋 일시

- **기록 일시:** 2026-04-21 (KST 기준, 외부 문의·인수인계용으로 전면 재작성)
- **최종 갱신:** 2026-04-21 — §1 **레이아웃 이슈 종료** 반영(사용자 확인: 꼼짝 없음)
- **저장소:** `roulette-1` (Flask + Flask-SocketIO + 단일 `templates/index.html` + Supabase)
- **이 문서의 목적:** 외부(다른 개발자·커뮤니티·벤더)에 질의할 때 붙여 넣을 수 있는 **현상·시도·환경** 요약

---

## 1) 게스트(Chrome) 레이아웃 점프 + 좌측 붙음 — **종료(2026-04-21)**

### 1.1 당시 현상

- **가로:** 루트 스크롤바 생김/사라짐에 따라 **본문이 좌우로 “한 칸” 밀리는** 느낌(Layout shift). thumb 길이 변화 자체는 부차적.
- **정렬:** `flex` + `margin: auto`만으로는 **게스트에서 메인이 왼쪽에 붙은 채** 넓은 화면이 휑해 보임(“끔찍할 정도” 피드백).

### 1.2 확정한 원인 요약

1. **`#main-container { justify-content: center }`** — 가용 너비가 스크롤바 등으로 바뀔 때마다 **가로 flex 행 전체가 재중앙**되며 밀림.
2. **`body { align-items: center }`** + flex 자식 — 교차축에서 **폭·정렬이 흔들릴 여지**.
3. **`100vw` / `92vw`** — 세로 스크롤 유무와 **가로 재계산**이 맞물림.
4. **`#main-container`만 `width: 100%` + `margin: 0 auto`** — `body`가 `display: flex`일 때 자식이 **가로 100%로 풀리면** `margin: auto`가 **좌우 여백을 못 나눔** → 게스트도 **왼쪽 붙음**처럼 보임.

### 1.3 최종 해결 구조 (`templates/index.html`)

| 레이어 | 역할 |
|--------|------|
| **`html`** | `overflow-y: scroll !important`, `scrollbar-gutter: stable`, `height: 100%` — **스크롤 트랙 자리 고정**(재미니 “safe centering”과 정합). |
| **`body`** | `flex-direction: column`, **`align-items: stretch`**, `overflow-y: visible` — 루트만 세로 스크롤. |
| **`.layout-shell`** | **`#header` + `#controls` + `#main-container`**를 한 블록으로 감쌈. `width: min(100%, 1600px)`, `margin-left/right: auto`, `align-self: center` — **flex 자식 단독으로는 안 되던 중앙 정렬**을 블록 단위로 해결. |
| **`#main-container`** | **`justify-content: flex-start`** 유지(행 재중앙으로 인한 밀림 제거). 폭은 셸 안에서 `width: 100%`. |
| **모바일** (`max-width: 1200px`) | `.layout-shell`을 `align-self: stretch`, `margin: 0`, `max-width: 100%`로 풀폭. |
| **기타** | `@media`의 `vw` 제거·차트 `aspect-ratio`, 내부 패널 `scrollbar-gutter` 제거 등(`389410e`, `3975b29` 계열). |

- **운영자 전용** `#sound-controls`, `#operator-dashboard-wrap`은 **`.layout-shell` 밖** — 대시보드는 계속 넓게 쓸 수 있음.

### 1.4 커밋 타임라인 (이슈 마무리)

| 커밋 | 내용 |
|------|------|
| `d863c66` | `body` stretch + `#main-container` `justify-content: flex-start` (가로 점프 완화) |
| `d7dd46f` | `html` 스크롤 고정 강화 + `main`에 `margin: auto`·`min(100%,1600px)` 시도(단독으로는 한계) |
| `6e91f06` | **`.layout-shell` 도입** — 좌측 붙음·중앙 복구의 **결정타** |
| (선행) `389410e`, `3975b29`, `660db3e` 등 | `vw` 제거, 내부 `scrollbar-gutter`, 루트 `html` 스크롤 등 |

### 1.5 사용자 확인

- **“꼼짝을 안 한다”** — 가로 시프트·이중 스크롤 체감이 **해소된 상태로 보고**(2026-04-21).

### 1.6 재발·회귀 시 (재미니 체크리스트 요약)

- DevTools로 **스크롤이 실제로 붙는 노드** 확인(가짜 루트).
- `justify-content: center`를 **가로 행 전체**에 다시 쓰지 않기.
- **`layout-shell`을 깨거나** `body`를 다시 `align-items: center`만 두지 않기.
- 임시 분기용 CSS는 아래(필요 시만 로컬).

```css
html { overflow-y: scroll !important; }
body, #main-container { overflow-y: visible !important; height: auto !important; min-height: 100vh; }
```

---

## 2) 최근에 잡힌 이슈(DB / 당첨자 리셋) — 참고만

- Supabase `participants` 테이블에 **`id` NOT NULL + default 없음** + 정수 PK 등으로 **`save`/당첨자 리셋 시 23502·22P02**가 연쇄 발생.
- 앱 쪽에서 **정수 PK면 `max(id)+1` 보강**, **UUID면 클라이언트 uuid**, **`created_at` 보강**, **작성자 키 NFC 정규화** 등으로 완화·해결 시도.  
- 대표 커밋: `585ae42`, `a6f259f`, `e1bfa60`, `f14758e` 등.  
- **운영 권장:** 장기적으로는 DB에 `id`용 **`GENERATED …` / `DEFAULT gen_random_uuid()`** 등을 두는 것이 안전.

---

## 3) 코드베이스에서 외부가 먼저 보면 좋은 파일

- `templates/index.html` — 거의 모든 UI/CSS/클라이언트 소켓·룰렛 애니메이션
- `comment_dart.py` — 라우트·SocketIO·게스트/운영자 분기
- `standalone_comment_monitor/db_handler.py` — Supabase 읽기/쓰기
- `.cursor/rules/vibe-basic-guardrails.mdc` — **타이밍 상수 임의 변경 금지** 등 프로젝트 가드레일

---

## 4) 운영 시 주의(이전 help에서 이어지는 원칙 요약)

- **타이밍 상수**(`ROULETTE_STOP_COMP_MS`, `ROULETTE_ANGLE_COMP_DEG`, `NETWORK_LAG_COMP_MAX_MS` 등)는 **증거 없이 변경하지 말 것**.
- `help.md`는 **사용자가 수정하라고 할 때만** 편집하는 것을 선호함(이번 항목은 **명시적 요청**으로 작성).

---

## 5) 다음 액션 (레이아웃 회귀 시)

1. **§1.3·§1.6** 순서로 원인 좁히기 — `.layout-shell` 포함 여부, `justify-content`, `body` `align-items`.
2. **DevTools**로 스크롤 소유 노드 확인 후 최소 패치(타이밍 상수·룰렛 로직은 건드리지 않기).
3. UI 대수정 전 **게스트·운영자·좁은/넓은 창** 각각 한 번씩 확인.

---

*끝.*
