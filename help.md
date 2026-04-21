# 룰렛 프로젝트 help.md (리셋본)

## 문서 리셋 일시

- **기록 일시:** 2026-04-21 (KST 기준, 외부 문의·인수인계용으로 전면 재작성)
- **저장소:** `roulette-1` (Flask + Flask-SocketIO + 단일 `templates/index.html` + Supabase)
- **이 문서의 목적:** 외부(다른 개발자·커뮤니티·벤더)에 질의할 때 붙여 넣을 수 있는 **현상·시도·환경** 요약

---

## 1) 지금 가장 시급한 미해결: 게스트(Chrome) 레이아웃 점프

### 사용자가 말하는 문제(한 줄)

- **게스트 모드 Chrome**에서, 페이지 **바깥(브라우저 루트) 세로 스크롤바가 생겼다/사라졌다** 할 때마다 **스크롤바 두께만큼 콘텐츠가 가로로 밀렸다 돌아오는** 현상이 반복됨.  
- 스크롤바 **thumb 길이**가 변하는 것 자체는 문제 삼지 않음. **가로로 흔들리는 것**이 핵심.

### 운영자 탭과의 차이

- 같은 `templates/index.html`을 쓰지만, **운영자(로그인) 탭에서는 거의 안정**이고 **게스트(비로그인)에서만** 체감이 큼(동일 기기·브라우저에서도 재현 패턴이 다를 수 있음).

### 외부에 물을 때 포함하면 좋은 가설(기술)

1. **뷰포트 vs 스크롤바 폭**  
   문서 높이가 뷰포트 높이 경계 근처에서 변동하면(애니메이션·폰트·이미지·실시간 DOM 갱신 등) **overlay가 아닌 클래식 스크롤바**가 붙었다 떨어지면서 **레이아웃 폭이 바뀜**.

2. **`100vw` / `vw` 단위**  
   일부 브라우저에서 `100vw`가 **세로 스크롤바 유무와 함께 달라지는 값**과 맞물려, 스크롤바 토글 시 **가로 재배치**가 발생할 수 있음.  
   → 코드에서 해당 구간을 `100%` 등으로 바꾸는 패치를 적용했으나 **사용자 체감상 동일**이라고 보고됨.

3. **`scrollbar-gutter: stable` 한계**  
   `html { overflow-y: scroll; scrollbar-gutter: stable; }`로 **루트만** 고정하려 했음.  
   Chrome/게스트/윈도우 조합에서 **기대만큼 루트에만 스크롤이 고정되지 않거나**, 다른 요소가 **또 하나의 스크롤 컨테이너**가 되어 **시각적으로 이중 스크롤 + 폭 변화**가 겹칠 수 있음.

4. **내부 스크롤 + 문서 스크롤**  
   `#prize-list`, `#memo-content-scroll`, `#all-participants-container` 등 `max-height` + `overflow-y: auto` 영역이 있어, **문서 스크롤과 패널 스크롤이 동시에 존재**할 수 있음. 사용자는 이를 “스크롤이 두 개”로 인지하기도 함.

### 이미 시도한 코드 방향(요약, 커밋 해시)

| 방향 | 대표 커밋 | 비고 |
|------|-----------|------|
| `html`에 `overflow-y: scroll` + `scrollbar-gutter: stable`, `body`는 `overflow-y: visible`로 이중 루트 스크롤 완화 | `660db3e` 계열 | 깜빡임 완화에는 도움이 됐다는 피드백도 있었음 |
| 내부 패널의 `scrollbar-gutter` 제거, 참가자 목록 `scroll`→`auto` | `3975b29` | 이중 스크롤 “느낌” 완화 목적 |
| `@media` 내 `100vw`/`92vw` 제거, `100%`·`min(100%,600px)`·`aspect-ratio`, 로딩 카드 `vw` 제거 | `389410e` | 스크롤바 토글 시 가로 밀림 방지 목적 — **사용자 피드백: 여전히 동일** |

### 재현 시나리오(외부에 전달용)

1. Chrome에서 **게스트 URL**으로 접속 (비로그인).
2. 이벤트가 로드된 상태에서 **룰렛 진행·사은품 목록 갱신·남은 시간 애니메이션** 등으로 화면이 바뀌는 구간을 수 분 관찰.
3. **브라우저 창 오른쪽**에서 문서 레벨 스크롤바가 나타났다 사라질 때, **본문 전체가 좌우로 한 칸 밀리는지** 확인.

### 외부에 그대로 던질 질문 예시

- “**단일 페이지 SPA가 아닌** 서버 렌더 Jinja + 긴 `index.html` 안에서, **Chrome 게스트만** 루트 스크롤바 토글과 함께 **가로 레이아웃 시프트**가 남는데, `html { overflow-y: scroll; scrollbar-gutter: stable }` + `vw` 제거 후에도 동일하면 **다음으로 의심할 체크리스트**(overflow propagation, flex + align-items, fixed 요소, `transform`/`filter` 레이어, Chrome 게스트 프로필 차이 등)는?”

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

## 5) 다음 액션(외부 답변 받은 뒤)

1. 게스트 스크롤/가로 시프트: **재현 영상 또는 Chrome Performance + 스크린 녹화**와 함께 외부 답변 반영.
2. 필요 시 **`index.html`의 `html/body/#main-container`만** 최소 패치로 분리 PR.

---

*끝. 이전 help.md 본문은 이 리셋본으로 대체됨.*
