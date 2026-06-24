import { useState, useRef, useEffect } from 'react'
import './App.css'

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage() {
    if (!input.trim() || loading) return

    const question = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: question }])
    setLoading(true)

    try {
      const res = await fetch('http://localhost:8000/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      if (!res.ok) throw new Error(`서버 오류 ${res.status}`)
      const data = await res.json()
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: data.answer,
        citations: data.citations,
        grounding: data.grounding_level,
        latency: data.latency_total_ms,
      }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'error', text: `연결 실패: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>국회 회의록 검색</h1>
        <span className="subtitle">외교통일위원회 · RAG</span>
      </header>

      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <p>질문을 입력하면 회의록에서 근거를 찾아 답변합니다.</p>
            <p className="hint">예: 조태열 장관의 대북 정책 입장은?</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <Message key={i} msg={msg} />
        ))}
        {loading && (
          <div className="loading">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
            검색 중...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="input-area">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="질문을 입력하세요 (Enter로 전송, Shift+Enter로 줄바꿈)"
          rows={2}
          disabled={loading}
        />
        <button onClick={sendMessage} disabled={loading || !input.trim()}>
          전송
        </button>
      </div>
    </div>
  )
}

function Message({ msg }) {
  if (msg.role === 'user') {
    return <div className="message user">{msg.text}</div>
  }
  if (msg.role === 'error') {
    return <div className="message error">{msg.text}</div>
  }
  return (
    <div className="message assistant">
      <GroundingBadge level={msg.grounding} />
      <div className="answer-text">{msg.text}</div>
      {msg.citations?.length > 0 && <CitationsTable citations={msg.citations} />}
      {msg.latency && (
        <div className="latency">{(msg.latency / 1000).toFixed(1)}초</div>
      )}
    </div>
  )
}

function GroundingBadge({ level }) {
  const map = {
    FULL: { label: '근거 충분', color: '#2d6a4f' },
    PARTIAL: { label: '부분 근거', color: '#6a4a2d' },
    NONE: { label: '근거 부족', color: '#5a2a2a' },
  }
  const style = map[level] || map.NONE
  return (
    <span className="badge" style={{ background: style.color }}>
      {style.label}
    </span>
  )
}

function CitationsTable({ citations }) {
  return (
    <div className="citations">
      <h4>참고 자료</h4>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>회의일</th>
            <th>발언자</th>
            <th>내용</th>
          </tr>
        </thead>
        <tbody>
          {citations.map(c => (
            <tr key={c.index}>
              <td>{c.index}</td>
              <td>{c.date || '—'}</td>
              <td>{c.speaker || '미상'}</td>
              <td className="preview">{c.content_preview}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
