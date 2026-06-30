import { COMMITTEE_SHORT } from './appConstants'
import CitationsTable from './CitationsTable'

export default function Message({ msg, selectedCitation, onCitationSelect }) {
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
  if (msg.needsClarification || msg.clarificationQuestion) {
    return <ClarificationCard msg={msg} />
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
      <CommitteeSourceSummary citations={msg.citations} />
      <FormattedAnswer text={msg.text} citations={msg.citations} onCitationClick={onCitationSelect} />
      {msg.citations?.length > 0 && (
        <CitationsTable
          citations={msg.citations}
          citationSort={msg.citationSort}
          selectedCitation={selectedCitation}
          onSelect={onCitationSelect}
        />
      )}
    </article>
  )
}

function ClarificationCard({ msg }) {
  const question = msg.clarificationQuestion || msg.text || '질문 범위를 조금 더 좁혀 주세요.'
  const options = Array.isArray(msg.clarificationOptions) ? msg.clarificationOptions : []

  return (
    <article className="clarification-card">
      <div className="clarification-header">
        <span className="card-label">추가 확인</span>
        <span className="badge badge-refused">범위 확인</span>
      </div>
      <p className="clarification-title">질문 범위를 조금 더 좁혀 주세요.</p>
      <p className="clarification-text">{question}</p>
      {options.length > 0 && (
        <div className="clarification-options">
          {options.map((option, i) => {
            const label = typeof option === 'string'
              ? option
              : option.label || option.text || `선택 ${i + 1}`
            return <span key={`${label}-${i}`} className="clarification-option">{label}</span>
          })}
        </div>
      )}
    </article>
  )
}

function getCommitteeDistribution(citations = []) {
  const counts = new Map()
  citations.forEach(c => {
    const committee = c.committee || '출처 미상'
    counts.set(committee, (counts.get(committee) || 0) + 1)
  })
  return Array.from(counts.entries())
    .map(([committee, count]) => ({
      committee,
      label: COMMITTEE_SHORT[committee] || committee,
      count,
    }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'ko'))
}

function CommitteeSourceSummary({ citations }) {
  const distribution = getCommitteeDistribution(citations)
  if (distribution.length === 0) return null

  return (
    <div className="source-summary" aria-label="근거 출처 분포">
      <span className="source-summary-label">근거 출처</span>
      <div className="source-summary-list">
        {distribution.map(item => (
          <span key={item.committee} className="source-summary-pill">
            {item.label} {item.count}건
          </span>
        ))}
      </div>
    </div>
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
    .replace(/([^\n])(#{1,4}\s)/g, '$1\n\n$2')
    .replace(/^(#{1,4})([^\s#\n])/gm, '$1 $2')
    .replace(/([^\n])(\n- )/g, '$1\n\n- ')
    .replace(/([^\n])(- \*\*)/g, '$1\n- **')
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
      if (!headText) return
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
