import { useState, useRef, useEffect } from 'react'
import './App.css'

const SESSION_KEY = 'na_rag_mock_session'
const API_BASE = 'http://localhost:8001'

const COMMITTEES = [
  { label: '전체', value: null },
  { label: '외교통일', value: '외교통일위원회' },
  { label: '정무', value: '정무위원회' },
  { label: '과기정통', value: '과학기술정보방송통신위원회' },
]

const EXAMPLE_QUESTIONS_BY_COMMITTEE = {
  null: [
    '조태열 장관의 대북 정책 입장은?',
    '금융위원장 은행 금리 규제에 대한 입장은?',
    'SKT 유심 해킹 사태에 대한 국회 논의는?',
  ],
  '외교통일위원회': [
    '오물 풍선에 대해 부정적으로 발언한 사람은?',
    '조태열 장관의 대북 정책 입장은?',
    '대북전단 관련 여야 입장을 정리해줘',
  ],
  '정무위원회': [
    '금융위원장 인사청문회에서 어떤 쟁점이 있었나요?',
    '기업은행 파업 문제에 대한 정무위 논의는?',
    '은행 금리 규제에 대한 여야 입장은?',
  ],
  '과학기술정보방송통신위원회': [
    'SKT 유심 해킹 사태에 대한 과기정통위 논의는?',
    '방송통신위원장 인사청문회 주요 쟁점은?',
    '공영방송 독립성 관련 여야 입장은?',
  ],
}

const FEATURES = [
  {
    title: '답변과 근거를 함께',
    desc: '회의록 원문 근거를 함께 확인할 수 있습니다.',
  },
  {
    title: '발언 맥락 추적',
    desc: '누가 언제 어떤 맥락에서 발언했는지 확인할 수 있습니다.',
  },
  {
    title: '쟁점 정리 지원',
    desc: '반복적인 회의록 검색 시간을 줄이고 쟁점 파악을 돕습니다.',
  },
]

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveSession(user) {
  localStorage.setItem(SESSION_KEY, JSON.stringify({
    ...user,
    mock: true,
    loggedInAt: new Date().toISOString(),
  }))
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY)
}

export default function App() {
  const [user, setUser] = useState(() => loadSession())
  const [page, setPage] = useState('chat')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedCommittee, setSelectedCommittee] = useState(null)

  const isAuthenticated = user != null

  function handleLogin(credentials) {
    saveSession(credentials)
    setUser(credentials)
  }

  function handleLogout() {
    clearSession()
    setUser(null)
    setMessages([])
    setInput('')
    setLoading(false)
    setPage('chat')
  }

  if (!isAuthenticated) {
    return <LoginIntroPage onLogin={handleLogin} />
  }

  if (page === 'meetings') {
    return (
      <MeetingExplorerPage
        user={user}
        currentPage={page}
        onNavigate={setPage}
        onLogout={handleLogout}
      />
    )
  }

  return (
    <ResearchWorkspacePage
      user={user}
      messages={messages}
      setMessages={setMessages}
      input={input}
      setInput={setInput}
      loading={loading}
      setLoading={setLoading}
      onLogout={handleLogout}
      currentPage={page}
      onNavigate={setPage}
      selectedCommittee={selectedCommittee}
      setSelectedCommittee={setSelectedCommittee}
    />
  )
}

/* ── Page 1: 로그인 + 소개 ─────────────────────────────── */

function LoginIntroPage({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!username.trim() || !password.trim()) {
      setError('아이디와 비밀번호를 입력해 주세요.')
      return
    }
    setError('')
    onLogin({ username: username.trim(), displayName: username.trim() })
  }

  function handleDemoLogin() {
    setError('')
    onLogin({ username: 'demo', displayName: '데모 사용자' })
  }

  return (
    <div className="login-page">
      <div className="login-layout">
        <section className="intro-panel">
          <p className="intro-eyebrow">외교통일위원회 회의록</p>
          <h1 className="intro-title">회의록으로 확인하는 정책 근거</h1>
          <p className="intro-subtitle">
            발언자, 회의일, 원문 근거를 연결해 정책 쟁점을 빠르게 검토합니다.
          </p>

          <ul className="intro-list">
            <li>회의록에서 관련 발언과 근거를 찾아 정책 질의에 답변합니다.</li>
            <li>답변에는 회의일, 발언자, 참고 근거가 함께 제공됩니다.</li>
            <li>국회·연구기관·정책 실무·언론 리서치 업무에 적합한 검색 환경을 제공합니다.</li>
          </ul>

          <div className="feature-grid">
            {FEATURES.map(f => (
              <div key={f.title} className="feature-item">
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="login-panel">
          <div className="login-box">
            <h2>로그인</h2>
            <p className="login-notice">
              현재는 시연용 로그인입니다. 아이디와 비밀번호를 입력하거나 데모 로그인을 사용할 수 있습니다.
            </p>

            <form onSubmit={handleSubmit} className="login-form">
              <label className="field-label" htmlFor="username">아이디 또는 이메일</label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="user@example.com"
              />

              <label className="field-label" htmlFor="password">비밀번호</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="비밀번호"
              />

              {error && <p className="login-error" role="alert">{error}</p>}

              <button type="submit" className="btn-primary">로그인</button>
              <button type="button" className="btn-secondary" onClick={handleDemoLogin}>
                데모 로그인
              </button>
            </form>
          </div>
        </section>
      </div>
    </div>
  )
}

/* ── Page 2: LLM 질의응답 ─────────────────────────────── */

function ResearchWorkspacePage({
  user,
  messages,
  setMessages,
  input,
  setInput,
  loading,
  setLoading,
  onLogout,
  currentPage,
  onNavigate,
  selectedCommittee,
  setSelectedCommittee,
}) {
  const bottomRef = useRef(null)
  const [selectedCitation, setSelectedCitation] = useState(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    if (!selectedCitation) return
    function onKeyDown(e) {
      if (e.key === 'Escape') setSelectedCitation(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedCitation])

  async function submitQuestion(questionText) {
    const question = questionText.trim()
    if (!question || loading) return

    // 현재 메시지에서 히스토리 빌드 (새 질문 추가 전)
    const history = messages
      .filter(m => (m.role === 'user' || m.role === 'assistant') && m.text && !m.streaming)
      .slice(-6)
      .map(m => ({ role: m.role, content: m.text }))

    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: question }])
    setLoading(true)

    // 스트리밍 placeholder 추가
    setMessages(prev => [...prev, { role: 'assistant', text: '', streaming: true, grounding: null, citations: [], latency: null }])

    try {
      const res = await fetch(`${API_BASE}/query/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          committee: selectedCommittee,
          history: history.length > 0 ? history : null,
        }),
      })
      if (!res.ok) throw new Error(`서버 오류 ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.type === 'token') {
              setMessages(prev => {
                const msgs = [...prev]
                const last = msgs[msgs.length - 1]
                if (last?.role === 'assistant' && last.streaming)
                  msgs[msgs.length - 1] = { ...last, text: last.text + event.content }
                return msgs
              })
            } else if (event.type === 'done') {
              setMessages(prev => {
                const msgs = [...prev]
                const last = msgs[msgs.length - 1]
                if (last?.role === 'assistant')
                  msgs[msgs.length - 1] = {
                    ...last,
                    text: event.answer ?? last.text,
                    streaming: false,
                    grounding: event.grounding,
                    citations: event.citations,
                    latency: event.latency,
                  }
                return msgs
              })
              setLoading(false)
            } else if (event.type === 'error') {
              throw new Error(event.message)
            }
          } catch { /* JSON parse 실패는 무시 */ }
        }
      }
    } catch (e) {
      setMessages(prev => {
        const msgs = prev.filter(m => !(m.role === 'assistant' && m.streaming))
        return [...msgs, { role: 'error', text: `연결 실패: ${e.message}` }]
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={`workspace${selectedCitation ? ' workspace--panel-open' : ''}`}>
      <header className="workspace-header">
        <div className="workspace-header-left">
          <h1>국회 회의록 검색</h1>
          <span className="subtitle">국회 상임위원회 회의록 · 근거 기반 RAG</span>
        </div>
        <nav className="page-nav">
          <button
            className={`nav-tab${currentPage === 'chat' ? ' nav-tab--active' : ''}`}
            onClick={() => onNavigate('chat')}
          >질의응답</button>
          <button
            className={`nav-tab${currentPage === 'meetings' ? ' nav-tab--active' : ''}`}
            onClick={() => onNavigate('meetings')}
          >회의 탐색</button>
        </nav>
        <div className="workspace-header-right">
          <span className="user-label">{user.displayName || user.username}</span>
          <button type="button" className="btn-logout" onClick={onLogout}>로그아웃</button>
        </div>
      </header>

      <main className="results">
        {messages.length === 0 && !loading && (
          <div className="empty">
            <p className="empty-title">회의록 근거 검색</p>
            <p className="empty-desc">
              위원회를 선택하고 질문을 입력하면 회의록에서 관련 발언을 찾아
              근거와 함께 답변합니다. 이전 대화 맥락을 이어받아 후속 질문도 가능합니다.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <Message
            key={i}
            msg={msg}
            selectedCitation={selectedCitation}
            onCitationSelect={setSelectedCitation}
          />
        ))}

        {loading && messages[messages.length - 1]?.text === '' && (
          <div className="loading-card">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
            <span className="loading-text">회의록 근거 확인 중</span>
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      <QuestionInput
        input={input}
        setInput={setInput}
        loading={loading}
        onSubmit={submitQuestion}
        examples={EXAMPLE_QUESTIONS_BY_COMMITTEE[selectedCommittee] ?? EXAMPLE_QUESTIONS_BY_COMMITTEE[null]}
        selectedCommittee={selectedCommittee}
        onCommitteeChange={setSelectedCommittee}
      />

      {selectedCitation && (
        <>
          <div
            className="pdf-panel-backdrop"
            onClick={() => setSelectedCitation(null)}
            aria-hidden="true"
          />
          <PdfViewerPanel
            citation={selectedCitation}
            onClose={() => setSelectedCitation(null)}
          />
        </>
      )}
    </div>
  )
}

function QuestionInput({ input, setInput, loading, onSubmit, examples, selectedCommittee, onCommitteeChange }) {
  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit(input)
    }
  }

  return (
    <section className="search-panel">
      <div className="committee-selector">
        {COMMITTEES.map(c => (
          <button
            key={String(c.value)}
            type="button"
            className={`committee-tab${selectedCommittee === c.value ? ' committee-tab--active' : ''}`}
            onClick={() => onCommitteeChange(c.value)}
            disabled={loading}
          >
            {c.label}
          </button>
        ))}
      </div>
      <div className="search-box">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={selectedCommittee ? `${selectedCommittee} 회의록에서 검색` : '위원회를 선택하거나 전체 회의록에서 검색'}
          rows={2}
          disabled={loading}
        />
        <button
          type="button"
          onClick={() => onSubmit(input)}
          disabled={loading || !input.trim()}
        >
          검색
        </button>
      </div>
      <div className="example-chips">
        <span className="example-label">예시 질문</span>
        {examples.map(q => (
          <button
            key={q}
            type="button"
            className="chip"
            disabled={loading}
            onClick={() => onSubmit(q)}
          >
            {q}
          </button>
        ))}
      </div>
    </section>
  )
}

function Message({ msg, selectedCitation, onCitationSelect }) {
  if (msg.role === 'user') {
    return (
      <div className="question-card">
        <span className="card-label">질문</span>
        <p className="question-text">{msg.text}</p>
      </div>
    )
  }
  if (msg.role === 'error') {
    return (
      <div className="error-card" role="alert">
        <span className="error-icon">!</span>
        <p>{msg.text}</p>
      </div>
    )
  }
  return (
    <article className="answer-card">
      <div className="answer-header">
        <span className="card-label">답변</span>
        <GroundingBadge level={msg.grounding} />
        {msg.latency != null && (
          <span className="latency">{(msg.latency / 1000).toFixed(1)}초</span>
        )}
      </div>
      <FormattedAnswer text={msg.text} citations={msg.citations} onCitationClick={onCitationSelect} />
      {msg.citations?.length > 0 && (
        <CitationsTable
          citations={msg.citations}
          selectedCitation={selectedCitation}
          onSelect={onCitationSelect}
        />
      )}
    </article>
  )
}

function GroundingBadge({ level }) {
  const map = {
    FULL: { label: '근거 충분', className: 'badge-full' },
    PARTIAL: { label: '부분 근거', className: 'badge-partial' },
    NONE: { label: '근거 부족', className: 'badge-none' },
    REFUSED: { label: '확인 불가', className: 'badge-refused' },
  }
  const info = map[level] || map.NONE
  return <span className={`badge ${info.className}`}>{info.label}</span>
}

function renderInline(text, citations, onCitationClick) {
  const parts = text.split(/(\*\*[^*]+\*\*|\[\d+\])/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    if (/^\[\d+\]$/.test(part)) {
      const n = parseInt(part.slice(1, -1), 10)
      const cit = citations?.find(c => c.index === n)
      if (cit && onCitationClick) {
        return (
          <button
            key={i}
            className="ref-badge ref-badge--link"
            onClick={() => onCitationClick(cit)}
            title={`${cit.speaker || ''} ${cit.date || ''} 원문 보기`}
          >
            {part}
          </button>
        )
      }
      return <span key={i} className="ref-badge">{part}</span>
    }
    return part
  })
}

function normalizeMarkdown(text) {
  return text
    // ## 헤더 앞에 줄바꿈 보장
    .replace(/([^\n])(#{1,4}\s)/g, '$1\n\n$2')
    // #없이 붙은 헤더 (##메인결과 → ## 메인결과)
    .replace(/^(#{1,4})([^\s#\n])/gm, '$1 $2')
    // 리스트 아이템 앞 줄바꿈 보장
    .replace(/([^\n])(\n- )/g, '$1\n\n- ')
    .replace(/([^\n])(- \*\*)/g, '$1\n- **')
    // 헤더와 내용이 같은 줄에 있을 때 분리 (## 메인 결과 내용... → ## 메인 결과\n내용...)
    .replace(/^(#{1,4}\s+(?:메인\s*결과|세부\s*근거|핵심\s*결론|확인된\s*범위))\s+([^#\n].+)$/gm, '$1\n$2')
}

function FormattedAnswer({ text, citations, onCitationClick }) {
  if (!text) return null

  const lines = normalizeMarkdown(text).split('\n')
  const elements = []
  let listItems = []

  function flushList() {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="answer-list">
          {listItems}
        </ul>,
      )
      listItems = []
    }
  }

  lines.forEach((line, i) => {
    const trimmed = line.trim()
    if (!trimmed) {
      flushList()
      return
    }
    if (/^#{1,4}(\s|$)/.test(trimmed)) {
      flushList()
      const headText = trimmed.replace(/^#{1,4}\s*/, '')
      if (!headText) return  // 빈 헤더 스킵
      elements.push(
        <h3 key={i} className="answer-section">{renderInline(headText, citations, onCitationClick)}</h3>,
      )
    } else if (trimmed.startsWith('※')) {
      flushList()
      elements.push(
        <div key={i} className="note-box">{renderInline(trimmed, citations, onCitationClick)}</div>,
      )
    } else if (trimmed.startsWith('- ')) {
      listItems.push(<li key={i}>{renderInline(trimmed.slice(2), citations, onCitationClick)}</li>)
    } else {
      flushList()
      elements.push(<p key={i}>{renderInline(trimmed, citations, onCitationClick)}</p>)
    }
  })
  flushList()

  return <div className="answer-body">{elements}</div>
}

function toAbsoluteApiUrl(url) {
  if (!url) return null
  return url.startsWith('http') ? url : `${API_BASE}${url}`
}

function buildPdfSrc(citation) {
  const base = toAbsoluteApiUrl(citation?.pdf_url)
  if (!base) return null
  // PDF.js 커스텀 뷰어 사용: /pdfs/{source_id}/viewer?page=N&search=text
  const params = new URLSearchParams()
  if (citation.page) params.set('page', citation.page)
  if (citation.search_text) params.set('search', citation.search_text)
  const qs = params.toString()
  return `${base}/viewer${qs ? '?' + qs : ''}`
}

function buildPdfDownloadUrl(citation) {
  return toAbsoluteApiUrl(citation?.pdf_download_url || citation?.pdf_url)
}

function PdfViewerPanel({ citation, onClose }) {
  const pdfSrc = buildPdfSrc(citation)

  return (
    <aside className="pdf-panel" role="dialog" aria-labelledby="pdf-panel-title">
      <div className="pdf-panel-header">
        <h2 id="pdf-panel-title">원문 근거 보기</h2>
        <button type="button" className="pdf-panel-close" onClick={onClose} aria-label="닫기">
          ×
        </button>
      </div>

      <dl className="pdf-panel-meta">
        <div className="pdf-meta-row">
          <dt>회의일</dt>
          <dd>{citation.date || '—'}</dd>
        </div>
        <div className="pdf-meta-row">
          <dt>발언자</dt>
          <dd>{citation.speaker || '미상'}</dd>
        </div>
        <div className="pdf-meta-row">
          <dt>근거 번호</dt>
          <dd>[{citation.index}]</dd>
        </div>
        <div className="pdf-meta-row pdf-meta-row--full">
          <dt>내용 미리보기</dt>
          <dd>{citation.content_preview || '—'}</dd>
        </div>
      </dl>

      {pdfSrc ? (
        <div className="pdf-panel-viewer">
          <iframe
            title={`회의록 PDF — 근거 ${citation.index}`}
            src={pdfSrc}
            className="pdf-iframe"
          />
        </div>
      ) : (
        <div className="pdf-panel-empty">
          이 참고 자료에는 아직 PDF 원문 연결 정보가 없습니다.
        </div>
      )}
    </aside>
  )
}

/* ── Page 3: 회의 탐색 ─────────────────────────────── */

const UTTERANCE_COLORS = {
  question: '#2563eb',
  answer: '#16a34a',
  statement: '#6b7280',
  procedural: '#d1d5db',
}

const PARTY_COLORS = {
  '더불어민주당': '#1a56db',
  '국민의힘': '#e8230a',
  '조국혁신당': '#7c3aed',
}

const CORE_TIMELINE_LIMIT = 16
const CORE_QA_LIMIT = 8
const CORE_QA_CONFIDENCE = 0.6
const ISSUE_SCORE_LIMIT = 4

const ISSUE_LABEL_RULES = [
  { title: '투명성 센터 설치와 운영 공백', keywords: ['투명성 센터', '투명성센터'] },
  { title: '방송미디어통신진흥원 설립 및 법안 처리', keywords: ['방송미디어통신진흥원', '진흥원', '정보통신망법'] },
  { title: '가맹사업법 안건 처리와 의사일정 변경', keywords: ['가맹사업법', '가맹사업'] },
  { title: '법안 심사 방식과 안건 분리', keywords: ['전부개정안', '각각 안건', '안건이 논의', '법안은 전부개정안'] },
  { title: '예산 편성·집행 및 삭감 근거', keywords: ['예산', '삭감', '증액', '감액', '집행'] },
  { title: '대북 정책과 남북관계 대응', keywords: ['대북', '북한', '남북', '통일'] },
  { title: '금융 규제와 시장 감독', keywords: ['금융', '은행', '금리', '공정거래', '감독'] },
  { title: '방송·통신 정책과 기관 운영', keywords: ['방송', '통신', '미디어', '방통'] },
]

const GOV_ROLE_PATTERN = /(정부|장관|차관|위원장|부위원장|실장|원장|청장|처장|전문위원)/

function getMeetingKey(meeting) {
  return meeting?.source_id || meeting?.meeting_date || ''
}

function formatMeetingLabel(meeting) {
  if (!meeting) return ''
  if (meeting.meeting_label) return meeting.meeting_label
  if (meeting.meeting_session && meeting.meeting_round) {
    return `제${meeting.meeting_session}회 제${meeting.meeting_round}차 회의`
  }
  if (meeting.meeting_session) return `제${meeting.meeting_session}회 회의`
  if (meeting.meeting_round) return `제${meeting.meeting_round}차 회의`
  return ''
}

function getTurnKey(turn, fallbackIndex) {
  if (turn?.turn_index !== null && turn?.turn_index !== undefined) {
    return `turn:${turn.turn_index}`
  }
  return `row:${fallbackIndex}`
}

function getPairTurnKeys(pair) {
  return [pair.q_turn_index, pair.a_turn_index]
    .filter(v => v !== null && v !== undefined)
    .map(v => `turn:${v}`)
}

function isCoreTimelineTurn(turn) {
  if (!['question', 'answer'].includes(turn.utterance_type)) return false
  const preview = String(turn.content_preview || '').trim()
  const compact = preview.replace(/\s+/g, '')
  if (compact.length < 28) return false
  return !/^(네|예|알겠습니다|이상입니다|감사합니다|수고하셨습니다)[.!?,\s]*/.test(preview)
}

function getCoreQAPairs(pairs) {
  if (pairs.length <= CORE_QA_LIMIT) return pairs
  // importance(쟁점+길이+고유명사+confidence 합산) 우선, 없으면 confidence fallback
  const byImportance = (a, b) => {
    const diff = Number(b.importance || b.confidence || 0) - Number(a.importance || a.confidence || 0)
    if (diff !== 0) return diff
    return Number(a.q_turn_index || 0) - Number(b.q_turn_index || 0)
  }
  const trusted = pairs.filter(p => !p.needs_review && Number(p.confidence || 0) >= CORE_QA_CONFIDENCE)
  const candidates = trusted.length ? trusted : pairs.filter(p => !p.needs_review)
  const source = candidates.length ? candidates : pairs
  return [...source].sort(byImportance).slice(0, CORE_QA_LIMIT)
}

function getCoreTimelineTurns(turns, qaPairs) {
  if (turns.length <= CORE_TIMELINE_LIMIT) return turns

  const selectedKeys = new Set()
  for (const pair of getCoreQAPairs(qaPairs)) {
    for (const key of getPairTurnKeys(pair)) selectedKeys.add(key)
  }

  for (let i = 0; i < turns.length && selectedKeys.size < CORE_TIMELINE_LIMIT; i += 1) {
    const key = getTurnKey(turns[i], i)
    if (!selectedKeys.has(key) && isCoreTimelineTurn(turns[i])) {
      selectedKeys.add(key)
    }
  }

  const coreTurns = turns.filter((turn, i) => selectedKeys.has(getTurnKey(turn, i)))
  return coreTurns.length ? coreTurns.slice(0, CORE_TIMELINE_LIMIT) : turns.slice(0, CORE_TIMELINE_LIMIT)
}

function getPrimaryParty(overview) {
  const entries = Object.entries(overview.party_distribution || {})
    .filter(([, count]) => Number(count) > 0)
    .sort(([, a], [, b]) => Number(b) - Number(a))
  return entries[0]?.[0] || null
}

function inferIssueTitle(text = '', fallback = '주요 쟁점') {
  const normalized = String(text).replace(/\s+/g, ' ').trim()
  for (const rule of ISSUE_LABEL_RULES) {
    if (rule.keywords.some(keyword => normalized.includes(keyword))) return rule.title
  }
  const compact = normalized
    .replace(/^(저는|그런데|일단|그러면|그리고|왜)\s*/, '')
    .replace(/[?？].*$/, '')
    .trim()
  if (!compact) return fallback
  return summarizeText(compact, 34)
}

function countKeywordHits(text = '', keywords = []) {
  const normalized = String(text).replace(/\s+/g, ' ')
  return keywords.reduce((sum, keyword) => sum + (normalized.includes(keyword) ? 1 : 0), 0)
}

function getMatchedIssueRule(text = '') {
  let best = null
  let bestHits = 0
  for (const rule of ISSUE_LABEL_RULES) {
    const hits = countKeywordHits(text, rule.keywords)
    if (hits > bestHits) {
      best = rule
      bestHits = hits
    }
  }
  return best ? { rule: best, hits: bestHits } : null
}

function isGovernmentSignal(...values) {
  return values.some(value => GOV_ROLE_PATTERN.test(String(value || '')))
}

function createIssueCandidate(title) {
  return {
    title,
    frequency: 0,
    qaCount: 0,
    govAnswerCount: 0,
    keywordHits: 0,
    textLength: 0,
    tagBoost: 0,
    speakers: new Set(),
    evidence: [],
    responses: [],
  }
}

function addIssueEvidence(candidates, title, evidence) {
  if (!title) return
  if (!candidates.has(title)) candidates.set(title, createIssueCandidate(title))
  const candidate = candidates.get(title)
  const text = String(evidence.text || '').replace(/\s+/g, ' ').trim()
  const response = String(evidence.response || '').replace(/\s+/g, ' ').trim()

  candidate.frequency += evidence.frequency || 1
  candidate.qaCount += evidence.qa ? 1 : 0
  candidate.govAnswerCount += evidence.govAnswer ? 1 : 0
  candidate.keywordHits += evidence.keywordHits || 0
  candidate.textLength += text.length + response.length
  candidate.tagBoost += evidence.tagBoost || 0

  if (evidence.speaker) candidate.speakers.add(evidence.speaker)
  if (evidence.answerSpeaker) candidate.speakers.add(evidence.answerSpeaker)
  if (text && candidate.evidence.length < 3) candidate.evidence.push(text)
  if (response && candidate.responses.length < 2) candidate.responses.push(response)
}

function finalizeIssueCandidate(candidate) {
  const speakerCount = candidate.speakers.size
  const frequencyScore = Math.min(candidate.frequency, 10) * 3.5
  const speakerScore = Math.min(speakerCount, 6) * 4
  const qaScore = Math.min(candidate.qaCount, 3) * 8
  const govScore = candidate.govAnswerCount > 0 ? 8 : 0
  const keywordScore = Math.min(candidate.keywordHits, 6) * 3
  const densityScore = Math.min(Math.round(candidate.textLength / 420), 5)
  const tagScore = Math.min(candidate.tagBoost, 2) * 4
  const score = Math.min(100, Math.round(
    frequencyScore + speakerScore + qaScore + govScore + keywordScore + densityScore + tagScore
  ))

  const metrics = [
    `관련 발언 ${candidate.frequency}건`,
    `발언자 ${speakerCount}명`,
  ]
  if (candidate.qaCount > 0) metrics.push(`Q&A ${candidate.qaCount}건`)
  if (candidate.govAnswerCount > 0) metrics.push('정부측 답변 포함')

  return {
    title: candidate.title,
    score,
    metrics,
    body: candidate.evidence.length
      ? summarizeText(candidate.evidence[0], 128)
      : '관련 발언이 반복적으로 확인됩니다.',
    response: candidate.responses.length ? summarizeText(candidate.responses[0], 96) : '',
  }
}

function buildIssueBriefs(overview, qaPairs, turns) {
  const candidates = new Map()

  for (const tag of overview.issue_tags || []) {
    addIssueEvidence(candidates, tag, {
      text: `${tag} 관련 발언이 반복적으로 확인됩니다.`,
      keywordHits: 1,
      tagBoost: 1,
    })
  }

  for (const pair of qaPairs) {
    if (pair.needs_review && Number(pair.confidence || 0) < 0.45) continue
    const questionText = pair.q_summary || pair.q_preview || pair.q_full_text || ''
    const answerText = pair.a_summary || pair.a_preview || pair.a_full_text || ''
    const combined = `${questionText} ${answerText}`
    const match = getMatchedIssueRule(combined)
    const title = match?.rule.title || inferIssueTitle(combined, `쟁점 후보 ${candidates.size + 1}`)
    addIssueEvidence(candidates, title, {
      text: questionText,
      response: answerText,
      qa: true,
      govAnswer: Boolean(answerText) && isGovernmentSignal(pair.a_speaker_role, pair.a_speaker),
      keywordHits: match?.hits || 0,
      speaker: pair.q_speaker,
      answerSpeaker: pair.a_speaker,
    })
  }

  for (const turn of turns) {
    const text = turn.content_preview || ''
    if (!text || text.replace(/\s+/g, '').length < 28) continue
    const match = getMatchedIssueRule(text)
    if (!match) continue
    addIssueEvidence(candidates, match.rule.title, {
      text,
      keywordHits: match.hits,
      speaker: turn.speaker,
      govAnswer: turn.position_type === '정부측' || isGovernmentSignal(turn.speaker_role, turn.speaker),
    })
  }

  if (candidates.size === 0) {
    for (const turn of getCoreTimelineTurns(turns, qaPairs).slice(0, 3)) {
      addIssueEvidence(candidates, inferIssueTitle(turn.content_preview, turn.speaker || '주요 발언'), {
        text: turn.content_preview,
        speaker: turn.speaker,
        govAnswer: turn.position_type === '정부측' || isGovernmentSignal(turn.speaker_role, turn.speaker),
      })
    }
  }

  return Array.from(candidates.values())
    .map(finalizeIssueCandidate)
    .sort((a, b) => b.score - a.score)
    .slice(0, ISSUE_SCORE_LIMIT)
}

function buildMeetingSummary(overview, issues, qaPairs) {
  const topSpeakers = (overview.top_speakers || []).slice(0, 3).map(s => s.speaker).filter(Boolean)
  const primaryParty = getPrimaryParty(overview)
  const issueText = issues.length
    ? issues.slice(0, 2).map(issue => issue.title).join(', ')
    : '회의 진행 및 주요 발언'
  const summary = [
    `${overview.committee} ${overview.meeting_date} 회의의 주요 쟁점은 ${issueText}입니다.`,
    `총 ${overview.total_turns}건의 발언과 ${overview.speaker_count}명의 발언자가 확인되며, 정부측 답변은 ${overview.govt_turn_count}건입니다.`,
  ]

  if (topSpeakers.length > 0) {
    summary.push(`발언 흐름은 ${topSpeakers.join(', ')} 중심으로 형성되어 있어 해당 발언자와 정부측 답변을 우선 확인하면 맥락 파악이 빠릅니다.`)
  }
  if (primaryParty) {
    summary.push(`정당·기관별 발언량 기준으로는 ${primaryParty} 발언 비중이 가장 크게 나타납니다.`)
  }
  if (qaPairs.length > 0) {
    summary.push(`세부 근거와 문답 구조는 별도 핵심 Q&A 탭에서 확인하는 편이 적합합니다.`)
  }
  return summary
}

const COMMITTEE_SHORT = {
  '외교통일위원회': '외교통일',
  '과학기술정보방송통신위원회': '과기정통',
  '정무위원회': '정무',
}

function MeetingExplorerPage({ user, currentPage, onNavigate, onLogout }) {
  const [meetings, setMeetings] = useState([])
  const [selectedMeetingKey, setSelectedMeetingKey] = useState(null)
  const [overview, setOverview] = useState(null)
  const [turns, setTurns] = useState([])
  const [qaPairs, setQaPairs] = useState([])
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [detailView, setDetailView] = useState('brief')
  const [meetingQuery, setMeetingQuery] = useState('')
  const [meetingYear, setMeetingYear] = useState('전체')
  const [committeeFilter, setCommitteeFilter] = useState('전체')

  useEffect(() => {
    fetch(`${API_BASE}/meetings`)
      .then(r => r.json())
      .then(data => setMeetings(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  const meetingYears = Array.from(
    new Set(meetings.map(m => String(m.meeting_date || '').slice(0, 4)).filter(Boolean))
  )

  const committees = Array.from(
    new Set(meetings.map(m => String(m.committee || '')).filter(Boolean))
  ).sort()

  const normalizedMeetingQuery = meetingQuery.trim()
  const filteredMeetings = meetings.filter(m => {
    const date = String(m.meeting_date || '')
    const meetingLabel = formatMeetingLabel(m)
    const matchesYear = meetingYear === '전체' || date.startsWith(meetingYear)
    const matchesCommittee = committeeFilter === '전체' || m.committee === committeeFilter
    const matchesQuery = !normalizedMeetingQuery
      || date.includes(normalizedMeetingQuery)
      || meetingLabel.includes(normalizedMeetingQuery)
    return matchesYear && matchesCommittee && matchesQuery
  })
  const hasMeetingFilters =
    normalizedMeetingQuery.length > 0 || meetingYear !== '전체' || committeeFilter !== '전체'
  const selectedCommitteeName = COMMITTEE_SHORT[committeeFilter] || committeeFilter
  const selectedCommitteeCount = committeeFilter === '전체'
    ? meetings.length
    : meetings.filter(m => m.committee === committeeFilter).length
  const currentConditionLabel = [
    committeeFilter !== '전체' ? selectedCommitteeName : null,
    meetingYear !== '전체' ? meetingYear : null,
    normalizedMeetingQuery ? `"${normalizedMeetingQuery}"` : null,
  ].filter(Boolean).join(' · ')

  const coreQaCount = getCoreQAPairs(qaPairs).length
  const coreTurnCount = getCoreTimelineTurns(turns, qaPairs).length

  async function selectMeeting(meeting) {
    const meetingKey = getMeetingKey(meeting)
    if (!meetingKey || meetingKey === selectedMeetingKey) return
    const encodedMeetingKey = encodeURIComponent(meetingKey)
    setSelectedMeetingKey(meetingKey)
    setLoadingDetail(true)
    setOverview(null)
    setTurns([])
    setQaPairs([])
    setDetailView('brief')
    try {
      const [ov, tv, qa] = await Promise.all([
        fetch(`${API_BASE}/meetings/${encodedMeetingKey}/overview`).then(r => r.json()),
        fetch(`${API_BASE}/meetings/${encodedMeetingKey}/turns`).then(r => r.json()),
        fetch(`${API_BASE}/meetings/${encodedMeetingKey}/qa_pairs`).then(r => r.ok ? r.json() : []),
      ])
      setOverview(ov)
      setTurns(Array.isArray(tv) ? tv : [])
      setQaPairs(Array.isArray(qa) ? qa : [])
    } catch {
      setOverview(null)
      setTurns([])
      setQaPairs([])
    } finally {
      setLoadingDetail(false)
    }
  }

  return (
    <div className="workspace workspace--wide">
      <header className="workspace-header">
        <div className="workspace-header-left">
          <h1>국회 회의록 검색</h1>
          <span className="subtitle">국회 상임위원회 회의록 · 근거 기반 RAG</span>
        </div>
        <nav className="page-nav">
          <button
            className={`nav-tab${currentPage === 'chat' ? ' nav-tab--active' : ''}`}
            onClick={() => onNavigate('chat')}
          >질의응답</button>
          <button
            className={`nav-tab${currentPage === 'meetings' ? ' nav-tab--active' : ''}`}
            onClick={() => onNavigate('meetings')}
          >회의 탐색</button>
        </nav>
        <div className="workspace-header-right">
          <span className="user-label">{user.displayName || user.username}</span>
          <button type="button" className="btn-logout" onClick={onLogout}>로그아웃</button>
        </div>
      </header>

      <div className="explorer-layout">
        <aside className="meeting-list">
          <div className="meeting-list-header">
            <p className="meeting-list-title">회의 목록</p>
            <span className="meeting-list-total">전체 회의록 {meetings.length}건</span>
          </div>
          <div className="meeting-tools">
            <input
              className="meeting-search"
              type="search"
              value={meetingQuery}
              onChange={e => setMeetingQuery(e.target.value)}
              placeholder="날짜·회차 검색"
            />
            <div className="meeting-filter-group">
              <span className="meeting-filter-label">위원회</span>
              <div className="meeting-year-row">
                {['전체', ...committees].map(c => (
                  <button
                    key={c}
                    type="button"
                    className={`meeting-year-btn${committeeFilter === c ? ' meeting-year-btn--active' : ''}`}
                    onClick={() => setCommitteeFilter(c)}
                  >
                    {COMMITTEE_SHORT[c] || c}
                  </button>
                ))}
              </div>
            </div>
            <div className="meeting-filter-group">
              <span className="meeting-filter-label">연도</span>
              <div className="meeting-year-row">
                {['전체', ...meetingYears].map(year => (
                  <button
                    key={year}
                    type="button"
                    className={`meeting-year-btn${meetingYear === year ? ' meeting-year-btn--active' : ''}`}
                    onClick={() => setMeetingYear(year)}
                  >
                    {year}
                  </button>
                ))}
              </div>
            </div>
            {hasMeetingFilters && (
              <div className="meeting-filter-summary">
                {committeeFilter !== '전체' && (
                  <span>{selectedCommitteeName} 전체 {selectedCommitteeCount}건</span>
                )}
                <span>
                  현재 조건 {currentConditionLabel && `${currentConditionLabel} `}
                  {filteredMeetings.length}건
                </span>
              </div>
            )}
          </div>
          {meetings.length === 0 && (
            <p className="meeting-list-empty">불러오는 중...</p>
          )}
          {meetings.length > 0 && filteredMeetings.length === 0 && (
            <p className="meeting-list-empty">조건에 맞는 회의가 없습니다.</p>
          )}
          {filteredMeetings.map(m => {
            const meetingKey = getMeetingKey(m)
            const meetingLabel = formatMeetingLabel(m)
            return (
              <button
                key={meetingKey}
                className={`meeting-list-item${selectedMeetingKey === meetingKey ? ' meeting-list-item--active' : ''}`}
                onClick={() => selectMeeting(m)}
              >
                <span className="meeting-list-main">
                  <span className="meeting-date">{m.meeting_date}</span>
                  {meetingLabel && <span className="meeting-source">{meetingLabel}</span>}
                </span>
                {m.committee && committeeFilter === '전체' && (
                  <span className="meeting-committee-badge">{COMMITTEE_SHORT[m.committee] || m.committee}</span>
                )}
              </button>
            )
          })}
        </aside>

        <main className="explorer-detail">
          {!selectedMeetingKey && !loadingDetail && (
            <div className="explorer-empty">
              <p>왼쪽 목록에서 회의를 선택하면<br />개요와 핵심 브리핑이 표시됩니다.</p>
            </div>
          )}
          {loadingDetail && (
            <div className="explorer-loading">
              <span className="dot" /><span className="dot" /><span className="dot" />
              <span>회의 정보 불러오는 중...</span>
            </div>
          )}
          {!loadingDetail && overview && (
            <>
              <MeetingOverviewCard overview={overview} />
              <div className="detail-tabs">
                <button
                  className={`detail-tab${detailView === 'brief' ? ' detail-tab--active' : ''}`}
                  onClick={() => setDetailView('brief')}
                >
                  핵심 브리핑
                </button>
                <button
                  className={`detail-tab${detailView === 'qa' ? ' detail-tab--active' : ''}`}
                  onClick={() => setDetailView('qa')}
                >
                  핵심 Q&A {qaPairs.length > 0 && <span className="detail-tab-count">{coreQaCount}</span>}
                </button>
                <button
                  className={`detail-tab${detailView === 'timeline' ? ' detail-tab--active' : ''}`}
                  onClick={() => setDetailView('timeline')}
                >
                  주요 발언 {turns.length > 0 && <span className="detail-tab-count">{coreTurnCount}</span>}
                </button>
              </div>
              {detailView === 'brief' && (
                <MeetingBriefing
                  overview={overview}
                  turns={turns}
                  qaPairs={qaPairs}
                  onViewChange={setDetailView}
                />
              )}
              {detailView === 'qa' && <QAPairsView pairs={qaPairs} />}
              {detailView === 'timeline' && <TurnTimeline turns={turns} qaPairs={qaPairs} />}
            </>
          )}
        </main>
      </div>
    </div>
  )
}

function MeetingBriefing({ overview, turns, qaPairs, onViewChange }) {
  const topSpeakers = (overview.top_speakers || []).slice(0, 5)
  const issues = buildIssueBriefs(overview, qaPairs, turns)
  const summary = buildMeetingSummary(overview, issues, qaPairs)
  const primaryParty = getPrimaryParty(overview)
  const leadSpeaker = topSpeakers[0]

  return (
    <section className="briefing-card briefing-card--memo">
      <div className="briefing-memo-head">
        <div>
          <p className="briefing-kicker">핵심 브리핑</p>
          <h3>회의 요약과 주요 쟁점</h3>
        </div>
        <div className="briefing-actions">
          <button type="button" className="list-toggle-btn" onClick={() => onViewChange('qa')}>
            Q&A 상세
          </button>
          <button type="button" className="list-toggle-btn" onClick={() => onViewChange('timeline')}>
            발언 목록
          </button>
        </div>
      </div>

      <div className="briefing-memo-grid">
        <div className="briefing-panel briefing-panel--primary">
          <div className="summary-section">
            <div className="memo-section-title">
              <span>회의 요약</span>
            </div>
            <ul className="meeting-summary-list">
              {summary.map(item => <li key={item}>{item}</li>)}
            </ul>
          </div>

          <div className="issue-section">
            <div className="memo-section-title">
              <span>주요 쟁점</span>
              {issues.length > 0 && <span className="briefing-count">{issues.length}개</span>}
            </div>
            {issues.length > 0 ? (
              <div className="issue-brief-grid">
                {issues.map((issue, i) => (
                  <article key={`${issue.title}-${i}`} className="issue-brief-card">
                    <div className="issue-card-meta">
                      <span className="issue-index">{String(i + 1).padStart(2, '0')}</span>
                      <span className="issue-score">{issue.score}점</span>
                    </div>
                    <div>
                      <h4>{issue.title}</h4>
                      <div className="issue-metrics">
                        {issue.metrics.map(metric => <span key={metric}>{metric}</span>)}
                      </div>
                      <p>{issue.body}</p>
                      {issue.response && (
                        <p className="issue-response">답변 방향: {issue.response}</p>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="briefing-empty">이 회의에서 별도 쟁점으로 분류할 발언이 충분히 추출되지 않았습니다.</p>
            )}
          </div>
        </div>

        <aside className="briefing-panel briefing-panel--side">
          <div className="memo-section">
            <h4>빠른 지표</h4>
            <dl className="briefing-facts">
              <div>
                <dt>전체 발언</dt>
                <dd>{overview.total_turns}건</dd>
              </div>
              <div>
                <dt>발언자</dt>
                <dd>{overview.speaker_count}명</dd>
              </div>
              <div>
                <dt>정부측 답변</dt>
                <dd>{overview.govt_turn_count}건</dd>
              </div>
              <div>
                <dt>최다 발언자</dt>
                <dd>{leadSpeaker?.speaker || '미상'}</dd>
              </div>
              <div>
                <dt>주도 정당</dt>
                <dd>{primaryParty || '집계 없음'}</dd>
              </div>
            </dl>
          </div>

          <div className="memo-section">
            <h4>다음 확인</h4>
            <p className="briefing-empty">
              쟁점별 세부 문답은 핵심 Q&A 탭에서, 발언 순서와 맥락은 주요 발언 탭에서 확인하세요.
            </p>
          </div>
        </aside>
      </div>
    </section>
  )
}

function MeetingOverviewCard({ overview }) {
  const partyDistribution = overview.party_distribution || {}
  const issueTags = (overview.issue_tags || []).slice(0, 4)
  const topSpeakers = (overview.top_speakers || []).slice(0, 5)
  const totalPartyTurns = Object.values(partyDistribution).reduce((a, b) => a + b, 0)
  const meetingLabel = formatMeetingLabel(overview)

  return (
    <section className="overview-card">
      <div className="overview-head">
        <h2 className="overview-title">
          <span>{overview.meeting_date} · {overview.committee}</span>
          {meetingLabel && <span className="overview-source">{meetingLabel}</span>}
        </h2>

        <div className="overview-stats">
          <div className="stat-box">
            <span className="stat-num">{overview.total_turns}</span>
            <span className="stat-label">전체 발언</span>
          </div>
          <div className="stat-box">
            <span className="stat-num">{overview.speaker_count}</span>
            <span className="stat-label">발언자 수</span>
          </div>
          <div className="stat-box">
            <span className="stat-num">{overview.govt_turn_count}</span>
            <span className="stat-label">정부측 답변</span>
          </div>
        </div>
      </div>

      <div className="overview-insights">
        {totalPartyTurns > 0 && (
          <div className="party-dist">
            <p className="overview-section-label">정당별 발언</p>
            <div className="party-bars">
              {Object.entries(partyDistribution).map(([party, cnt]) => (
                <div key={party} className="party-row">
                  <span className="party-name" style={{ color: PARTY_COLORS[party] || '#374151' }}>
                    {party}
                  </span>
                  <div className="party-bar-wrap">
                    <div
                      className="party-bar-fill"
                      style={{
                        width: `${Math.round((cnt / totalPartyTurns) * 100)}%`,
                        background: PARTY_COLORS[party] || '#9ca3af',
                      }}
                    />
                  </div>
                  <span className="party-cnt">{cnt}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="overview-side">
          {issueTags.length > 0 && (
            <div className="issue-tags-section">
              <p className="overview-section-label">주요 쟁점</p>
              <div className="tag-list">
                {issueTags.map(tag => (
                  <span key={tag} className="issue-tag">{tag}</span>
                ))}
              </div>
            </div>
          )}

          {topSpeakers.length > 0 && (
            <div className="top-speakers">
              <p className="overview-section-label">주요 발언자</p>
              <div className="speaker-chips">
                {topSpeakers.map(s => (
                  <span key={s.speaker} className="speaker-chip">
                    <span
                      className="speaker-dot"
                      style={{
                        background: PARTY_COLORS[s.party] || (s.position_type === '정부측' ? '#16a34a' : '#9ca3af'),
                      }}
                    />
                    {s.speaker}
                    {s.speaker_role && <span className="speaker-role"> {s.speaker_role}</span>}
                    <span className="speaker-cnt">{s.turn_count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function TurnTimeline({ turns, qaPairs }) {
  const [showAll, setShowAll] = useState(false)
  if (!turns.length) return null

  const LABEL = {
    question: '질의',
    answer: '답변',
    procedural: '의사진행',
    statement: '발언',
  }

  const coreTurns = getCoreTimelineTurns(turns, qaPairs)
  const visibleTurns = showAll ? turns : coreTurns
  const hasHiddenTurns = visibleTurns.length < turns.length

  return (
    <section className="turn-timeline">
      <div className="section-heading-row">
        <p className="overview-section-label">
          {showAll ? '발언 타임라인' : '핵심 발언'} <span className="turn-count">({visibleTurns.length}/{turns.length}건)</span>
        </p>
        {hasHiddenTurns && (
          <button type="button" className="list-toggle-btn" onClick={() => setShowAll(v => !v)}>
            {showAll ? '핵심만' : '전체 보기'}
          </button>
        )}
      </div>
      <div className="turn-list">
        {visibleTurns.map((t, i) => (
          <div key={i} className="turn-item">
            <div
              className="turn-type-bar"
              style={{ background: UTTERANCE_COLORS[t.utterance_type] || '#d1d5db' }}
              title={t.utterance_type || ''}
            />
            <div className="turn-body">
              <div className="turn-meta">
                <span className="turn-speaker">{t.speaker || '미상'}</span>
                {t.speaker_role && <span className="turn-role">{t.speaker_role}</span>}
                {t.party && (
                  <span className="turn-party" style={{ color: PARTY_COLORS[t.party] || '#6b7280' }}>
                    {t.party}
                  </span>
                )}
                {t.position_type === '정부측' && !t.party && (
                  <span className="turn-party turn-party--govt">정부측</span>
                )}
                <span className={`turn-type-badge turn-type-${t.utterance_type}`}>
                  {LABEL[t.utterance_type] || '발언'}
                </span>
              </div>
              <p className="turn-preview">{t.content_preview}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function summarizeText(text = '', maxLen = 220) {
  const normalized = String(text).replace(/\s+/g, ' ').trim()
  if (normalized.length <= maxLen) return normalized
  const sliced = normalized.slice(0, maxLen)
  const lastSentence = Math.max(
    sliced.lastIndexOf('. '),
    sliced.lastIndexOf('? '),
    sliced.lastIndexOf('! '),
    sliced.lastIndexOf('다.'),
    sliced.lastIndexOf('요.'),
    sliced.lastIndexOf('다 '),
  )
  if (lastSentence > maxLen * 0.45) {
    return sliced.slice(0, lastSentence + 1).trim() + '…'
  }
  return sliced.trim() + '…'
}

function ConfidenceBadge({ value }) {
  const pct = Math.round(value * 100)
  let cls = 'qa-conf qa-conf--high'
  if (pct < 30) cls = 'qa-conf qa-conf--low'
  else if (pct < 55) cls = 'qa-conf qa-conf--mid'
  return <span className={cls} title="주제 일치 확신 점수">{pct}%</span>
}

function buildQAPdfCitation(pair, side) {
  const isQ = side === 'q'
  const sourceId = isQ ? pair.q_source_id : pair.a_source_id
  const pageNo   = isQ ? pair.q_page_no   : pair.a_page_no
  const speaker  = isQ ? pair.q_speaker   : pair.a_speaker
  const preview  = isQ ? pair.q_preview   : pair.a_preview
  return {
    index: isQ ? 'Q' : 'A',
    speaker,
    pdf_url: sourceId ? `/pdfs/${sourceId}` : null,
    pdf_download_url: sourceId ? `/pdfs/${sourceId}/download` : null,
    page: pageNo || null,
    content_preview: preview || '',
  }
}

function QAPairsView({ pairs }) {
  const [pdfCitation, setPdfCitation] = useState(null)
  const [showAll, setShowAll] = useState(false)

  if (!pairs.length) {
    return (
      <section className="qa-pairs">
        <p className="qa-empty">이 회의에서 질의-답변 쌍을 찾을 수 없습니다.</p>
      </section>
    )
  }

  const corePairs = getCoreQAPairs(pairs)
  const visiblePairs = showAll ? pairs : corePairs
  const hasHiddenPairs = visiblePairs.length < pairs.length
  const reviewCount = visiblePairs.filter(p => p.needs_review).length

  return (
    <section className="qa-pairs">
      {pdfCitation && (
        <>
          <div className="pdf-panel-backdrop" onClick={() => setPdfCitation(null)} />
          <PdfViewerPanel citation={pdfCitation} onClose={() => setPdfCitation(null)} />
        </>
      )}
      <div className="section-heading-row">
        <p className="overview-section-label">
          {showAll ? '질의-답변 쌍' : '핵심 질의-답변 쌍'} <span className="turn-count">({visiblePairs.length}/{pairs.length}건)</span>
          {reviewCount > 0 && (
            <span className="qa-review-count"> · 검토 필요 {reviewCount}건</span>
          )}
        </p>
        {hasHiddenPairs && (
          <button type="button" className="list-toggle-btn" onClick={() => setShowAll(v => !v)}>
            {showAll ? '핵심만' : '전체 보기'}
          </button>
        )}
      </div>
      {visiblePairs.map((pair, i) => {
        const qDisplay = pair.q_summary || summarizeText(pair.q_preview || pair.q_full_text, 220)
        const aDisplay = pair.a_summary || summarizeText(pair.a_preview || pair.a_full_text, 220)
        return (
          <div key={`${pair.q_turn_index || 'q'}-${pair.a_turn_index || 'a'}-${i}`} className={`qa-pair${pair.needs_review ? ' qa-pair--review' : ''}`}>
            {pair.needs_review && (
              <div className="qa-review-warning">⚠ 매칭 검토 필요 — 질의·답변 주제가 맞지 않을 수 있습니다</div>
            )}
            <div className="qa-question">
              <div className="qa-meta">
                <span className="qa-label qa-label--q">질의</span>
                <span className="qa-speaker">{pair.q_speaker || '미상'}</span>
                {pair.q_speaker_role && <span className="qa-role">{pair.q_speaker_role}</span>}
                {pair.q_party && (
                  <span className="qa-party" style={{ color: PARTY_COLORS[pair.q_party] || '#6b7280' }}>
                    {pair.q_party}
                  </span>
                )}
                <ConfidenceBadge value={pair.confidence} />
                <button
                  className="qa-source-btn"
                  onClick={() => setPdfCitation(buildQAPdfCitation(pair, 'q'))}
                  title="질의 원문 PDF 보기"
                >
                  질의 원문
                </button>
              </div>
              <p className="qa-preview">{qDisplay}</p>
            </div>
            <div className="qa-connector">
              <span className="qa-arrow">↓</span>
            </div>
            <div className="qa-answer">
              <div className="qa-meta">
                <span className="qa-label qa-label--a">답변</span>
                <span className="qa-speaker">{pair.a_speaker || '미상'}</span>
                {pair.a_speaker_role && <span className="qa-role">{pair.a_speaker_role}</span>}
                <button
                  className="qa-source-btn"
                  onClick={() => setPdfCitation(buildQAPdfCitation(pair, 'a'))}
                  title="답변 원문 PDF 보기"
                >
                  답변 원문
                </button>
              </div>
              <p className="qa-preview">{aDisplay}</p>
            </div>
          </div>
        )
      })}
    </section>
  )
}

function CitationsTable({ citations, selectedCitation, onSelect }) {
  return (
    <div className="citations">
      <h4 className="citations-title">참고 자료</h4>
      <p className="citations-hint">내용을 누르면 원문 viewer가 열리고, 파일 저장은 다운로드 버튼을 사용합니다.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>회의일</th>
              <th>발언자</th>
              <th>내용</th>
              <th>파일</th>
            </tr>
          </thead>
          <tbody>
            {citations.map(c => {
              const isSelected = selectedCitation?.index === c.index
                && selectedCitation?.content_preview === c.content_preview
              const downloadUrl = buildPdfDownloadUrl(c)
              return (
                <tr
                  key={c.index}
                  className={`citation-row${isSelected ? ' citation-row--selected' : ''}`}
                >
                  <td className="col-index">{c.index}</td>
                  <td className="col-date">{c.date || '—'}</td>
                  <td className="col-speaker">{c.speaker || '미상'}</td>
                  <td className="col-preview">
                    <button
                      type="button"
                      className="citation-content-button"
                      onClick={() => onSelect(c)}
                    >
                      <span>{c.content_preview || '내용 없음'}</span>
                      <span className="citation-open-label">원문 보기</span>
                    </button>
                  </td>
                  <td className="col-actions">
                    {downloadUrl ? (
                      <a
                        className="citation-download-button"
                        href={downloadUrl}
                        download
                        onClick={e => e.stopPropagation()}
                      >
                        다운로드
                      </a>
                    ) : (
                      <span className="citation-download-disabled">없음</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
