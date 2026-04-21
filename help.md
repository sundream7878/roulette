# 룰렛 프로젝트 help.md (리셋본)

## 문서 리셋 일시

- **기록 일시:** 2026-04-21 (KST 기준, 외부 문의·인수인계용으로 전면 재작성)
- **최종 갱신:** 2026-04-21 — §1.2~1.5에 외부 조언(**재미니**) 반영
- **저장소:** `roulette-1` (Flask + Flask-SocketIO + 단일 `templates/index.html` + Supabase)
- **이 문서의 목적:** 외부(다른 개발자·커뮤니티·벤더)에 질의할 때 붙여 넣을 수 있는 **현상·시도·환경** 요약

---

## 1) 지금 가장 시급한 미해결: 게스트(Chrome) 레이아웃 점프

### 1.1 사용자가 말하는 문제(한 줄)

- **게스트 모드 Chrome**에서, 페이지 **바깥(브라우저 루트) 세로 스크롤바가 생겼다/사라졌다** 할 때마다 **스크롤바 두께만큼 콘텐츠가 가로로 밀렸다 돌아오는** 현상이 반복됨.  
- 스크롤바 **thumb 길이**가 변하는 것 자체는 문제 삼지 않음. **가로로 흔들리는 것**이 핵심.

### 운영자 탭과의 차이

- 같은 `templates/index.html`을 쓰지만, **운영자(로그인) 탭에서는 거의 안정**이고 **게스트(비로그인)에서만** 체감이 큼(동일 기기·브라우저에서도 재현 패턴이 다를 수 있음).

### 1.2 왜 “한 번에” 안 잡히나 (외부 조언 요약 · 재미니)

- 이 이슈는 **문법 오류 한 줄**이 아니라, **브라우저 렌더링 + CSS 박스 모델 + DOM 스크롤 소유권(scrollport)**이 겹친 **고질적 UI/UX 문제**에 가깝다.
- 그래서 `html`에만 `overflow-y: scroll` / `scrollbar-gutter`를 줘도, **실제 스크롤이 다른 요소에서 토글**되면 증상이 남을 수 있다.

### 1.3 가로 레이아웃 시프트 — **다음 의심 체크리스트 (Next Suspects)**

#### (1) “가짜 루트” 스크롤러 (Inner scroll hijacking)

- `html { overflow-y: scroll; … }`를 줬는데도 실패한다면, **실제 스크롤이 `html`/`body`가 아닐 확률이 높다.**
- `#main-container`, `.wrapper` 류에 **`height: 100vh` + `overflow-y: auto`**가 있으면, 루트의 `scrollbar-gutter`와 무관하게 **내부 div에서 스크롤바가 토글**되며 안쪽 콘텐츠가 밀릴 수 있다.
- **확인:** Chrome DevTools에서 스크롤이 붙는 순간, 스크롤바를 잡고 **어느 노드가 스크롤 컨테이너인지** 호버로 추적한다.

#### (2) 중앙 정렬의 역설 (`margin: 0 auto` · flex `justify-content: center`)

- 스크롤바(윈도우 Chrome 기준 대략 15~17px)가 생기면 **가용 너비**가 줄어든다.
- 메인 블록이 **`margin: 0 auto` 또는 부모 `justify-content: center`**로 가운데 정렬이면, 가용 너비가 줄어들 때 **시각적 중심이 미세하게 이동**해 “좌우로 한 칸 밀린다”로 느껴질 수 있다.
- 대응 방향(참고): `max-width` 고정, 스크롤을 바깥으로 빼기, 필요 시 `padding-left: calc(100vw - 100%)` 류의 **부분적** 보정(부작용 검토 필수).

#### (3) `position: fixed` 요소

- 모달·플로팅·고정 헤더 등은 **뷰포트 기준**이라, 문서 쪽만 스크롤바 폭으로 밀리면 **fixed와 본문의 상대 위치가 어긋나 보일 수 있다.**

#### (4) 운영자 탭 vs 게스트 탭의 DOM 차이

- 운영자만 **항상 문서 높이가 뷰포트를 넘겨 스크롤바가 상시(Always-on)**이면, 게스트처럼 **경계에서 스크롤이 토글되는 상황 자체가 덜 생길 수 있다.** (대시보드 블록은 Jinja로 게스트에선 렌더되지 않음.)

### 1.4 Jinja + 단일 `index.html` — **디버깅용 CSS (임시 주입)**

아래는 **로컬에서만** `<head>` 끝 또는 `<style>` 맨 아래에 잠깐 넣어 **원인 분기**용이다. **운영 반영 전** 반드시 제거한다.

```css
/* 디버깅: 루트 스크롤 고정 */
html {
  overflow-y: scroll !important;
}

/* 내부가 스크롤을 가로채는지 확인 */
body,
#main-container {
  overflow-y: visible !important;
  height: auto !important;
  min-height: 100vh;
}
```

- **이 상태에서도** “스크롤이 또 생기며(이중) 밀린다” → **(1) 내부 스크롤 하이재킹** 가능성이 매우 높다 (다른 래퍼·패널을 계속 추적).
- **이 코드로 가로 시프트가 안정**된다면 → 본문 높이가 **뷰포트 경계를 넘나들며** 루트 스크롤이 토글되는 쪽이 원인 후보.

### 1.5 현재 `index.html` 스냅샷 (빠른 참고, 갱신 시 help도 수정)

- `html`: `overflow-y: scroll`, `scrollbar-gutter: stable`, `height: 100%`
- `body`: flex column, `align-items: center`, `width: 100%`, `min-height: 100%`, `overflow-y: visible` — **(2) 중앙 정렬 역설 후보**
- `#main-container`: `width: 100%`, `max-width: 1600px` — **당분간 `100vh` + 세로 `auto` 스크롤 래퍼는 없음**(문자열 검색 기준). 그래도 **동적 높이·미디어쿼리·자식 flex** 조합으로 문서 스크롤이 토글될 수 있음.
- 내부 패널: `#memo-content-scroll`, `#prize-list`, `#all-participants-container` 등에 `max-height` + `overflow-y: auto` 존재.

### 기존에 정리해 둔 가설(기술)

1. **뷰포트 vs 스크롤바 폭** — 문서 높이가 뷰포트 근처에서 변동하면 클래식 스크롤바 토글 + 폭 변화.
2. **`100vw` / `vw`** — 스크롤바 유무와 엮인 재계산. → `100%` 등으로 일부 교체했으나 **체감상 동일** 보고.
3. **`scrollbar-gutter: stable` 한계** — 실제 스크롤 소유자가 `html`이 아니면 기대와 다를 수 있음.
4. **내부 스크롤 + 문서 스크롤** — 이중 스크롤·시각적 혼동.

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

- “**단일 페이지 SPA가 아닌** 서버 렌더 Jinja + 긴 `index.html` 안에서, **Chrome 게스트만** 루트 스크롤바 토글과 함께 **가로 레이아웃 시프트**가 남는다. `html { overflow-y: scroll; scrollbar-gutter: stable }` + `vw` 제거 후에도 동일하다. **§1.3 체크리스트(가짜 루트 스크롤 / flex 중앙 정렬 / fixed / DOM 차이)**와 **§1.4 임시 CSS**로 분기했을 때 다음 단계로 무엇을 보면 좋은가?”

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

## 5) 다음 액션

1. **DevTools로 스크롤 소유 노드 확정** → §1.3 (1) 검증.
2. **§1.4 임시 CSS**로 분기(이중 스크롤 vs 루트 토글) 기록.
3. 필요 시 **`index.html`의 스크롤 소유자·body flex 정렬만** 최소 패치(가드레일 준수).
4. 외부 질의 시 **재현 영상** 첨부.

---

*끝.*
