import { useState, useRef, useEffect } from 'react'
import './App.css'

const SESSION_KEY = 'na_rag_mock_session'
const API_BASE = 'http://localhost:8001'

const EXAMPLE_QUESTIONS = [
  '오물 풍선에 대해서 부정적으로 대화한 사람은?',
  '조태열 장관의 대북 정책 입장은?',
  '대북전단 관련 주요 발언을 정리해줘',
]

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
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

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
  }

  if (!isAuthenticated) {
    return <LoginIntroPage onLogin={handleLogin} />
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

    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: question }])
    setLoading(true)

    // 스트리밍 placeholder 추가
    setMessages(prev => [...prev, { role: 'assistant', text: '', streaming: true, grounding: null, citations: [], latency: null }])

    try {
      const res = await fetch(`${API_BASE}/query/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
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
          <span className="subtitle">외교통일위원회 · 근거 기반 RAG</span>
        </div>
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
              질문을 입력하면 외교통일위원회 회의록에서 관련 발언을 찾아
              근거와 함께 답변합니다.
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
        examples={EXAMPLE_QUESTIONS}
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

function QuestionInput({ input, setInput, loading, onSubmit, examples }) {
  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit(input)
    }
  }

  return (
    <section className="search-panel">
      <div className="search-box">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="회의록에서 확인할 쟁점을 입력하세요"
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
