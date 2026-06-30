# React 전환 계획

> 프로토타입 → 풀스택 데모. Streamlit 제거, FastAPI + React로 재구성.
> 코드 작성 전 결정 사항 정리본.

---

## 1. 기술 스택 결정

| 영역 | 선택 | 이유 |
|------|------|------|
| 번들러/프레임워크 | **Vite + React** | CRA보다 빠름, Next.js는 SSR 불필요 |
| 언어 | **TypeScript** | API 응답 타입 명시, 인용 번호 연동 버그 예방 |
| 스타일 | **Tailwind CSS** | 빠른 UI 구성, 별도 CSS 파일 관리 불필요 |
| 상태관리 | **Zustand** | 채팅 히스토리·스트리밍 상태 관리, Redux 대비 단순 |
| 마크다운 | **react-markdown + remark-gfm** | `[n]` 인용 커스텀 렌더러 필요 |
| HTTP | **fetch API** (SSE), **axios** (일반) | 스트리밍은 fetch ReadableStream |

---

## 2. 백엔드 변경 사항 (api/main.py)

기존 엔드포인트는 그대로 두고 아래 두 가지만 추가.

### 2-1. CORS 미들웨어
```
허용 origin: http://localhost:5173 (Vite dev), 배포 시 실제 도메인
```

### 2-2. SSE 스트리밍 엔드포인트 신규
```
POST /query/stream
- Request: QueryRequest (기존 동일)
- Response: text/event-stream
  data: {"type": "chunk", "content": "..."}
  data: {"type": "citations", "data": [...]}
  data: {"type": "done", "grounding_level": "FULL"}
```

기존 `POST /query`는 유지 (폴백·테스트용).

### 2-3. citations 응답 보강
```
현재: content_preview[:120]
변경: chunk_text 전체 포함 (React 참고자료 패널에서 전문 표시)
```

---

## 3. React 앱 구조

```
frontend/
├── src/
│   ├── api/
│   │   ├── query.ts        # POST /query/stream SSE 클라이언트
│   │   └── meetings.ts     # GET /meetings
│   ├── store/
│   │   └── chat.ts         # Zustand: messages, streaming 상태
│   ├── components/
│   │   ├── ChatInput.tsx
│   │   ├── MessageList.tsx
│   │   ├── AssistantMessage.tsx   # 마크다운 + [n] 인용 렌더링
│   │   ├── CitationPanel.tsx      # 참고자료 펼침 영역
│   │   └── Sidebar.tsx            # 위원회·날짜 필터
│   └── App.tsx
├── index.html
└── vite.config.ts
```

---

## 4. 핵심 컴포넌트 동작

### AssistantMessage
- `react-markdown`으로 마크다운 렌더
- `[n]` 패턴을 커스텀 컴포넌트로 교체 → 클릭 시 해당 인용 하이라이트
- 스트리밍 중에는 커서 깜빡임 표시

### CitationPanel
- 답변 아래 접힘/펼침 (`<details>` 또는 커스텀 Accordion)
- 본문에서 실제 사용된 `[n]` 번호만 강조
- 청크 전문 보기 (토글)

### SSE 스트리밍 흐름
```
사용자 입력
  → fetch POST /query/stream
  → ReadableStream으로 chunk 수신하며 메시지에 append
  → done 이벤트 수신 시 citations 파싱 후 CitationPanel 표시
```

---

## 5. 구현 순서

### Phase 1 — 백엔드 준비 (반나절)
1. `api/main.py` CORS 추가
2. `POST /query/stream` SSE 엔드포인트 구현
3. citations 응답에 `chunk_text` 추가
4. `uvicorn` 실행 + Swagger로 수동 검증

### Phase 2 — React 뼈대 (반나절)
1. `npm create vite@latest frontend -- --template react-ts`
2. Tailwind 설정
3. Zustand store 구성
4. 기본 채팅 레이아웃 (입력창 + 메시지 목록)

### Phase 3 — 스트리밍 연동 (반나절)
1. SSE 클라이언트 구현
2. 스트리밍 중 실시간 렌더링
3. 완료 후 CitationPanel 표시

### Phase 4 — UI 마무리 (반나절)
1. `[n]` 인용 클릭 연동
2. 위원회·날짜 필터 사이드바
3. 로딩 상태, 에러 처리

---

## 6. Streamlit 처리 (완료)

- Streamlit 완전 제거 완료 — `app.py`, `pages/` 삭제됨
- FastAPI는 그대로 유지 (React의 API 서버)
- 프론트엔드는 React만 사용

---

## 결정하지 않은 것 (나중에)

- 인증/로그인 (지금은 없음)
- 배포 방식 (Vercel + Railway? Docker Compose?)
- 다크모드
- 모바일 대응
