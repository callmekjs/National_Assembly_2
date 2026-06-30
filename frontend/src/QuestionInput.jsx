import { useState } from 'react'
import {
  EXAMPLE_QUESTIONS_BY_COMMITTEE,
  QUESTION_COMMITTEE_FILTERS,
} from './appConstants'

export default function QuestionInput({
  input,
  setInput,
  loading,
  onSubmit,
  selectedCommittee,
  onCommitteeChange,
}) {
  const [filterOpen, setFilterOpen] = useState(false)
  const selectedFilter = QUESTION_COMMITTEE_FILTERS.find(c => c.value === selectedCommittee)
  const selectedLabel = selectedFilter?.label || '전체 자동'
  const examples = EXAMPLE_QUESTIONS_BY_COMMITTEE[selectedCommittee] ?? EXAMPLE_QUESTIONS_BY_COMMITTEE[null]
  const exampleLabel = selectedCommittee ? `${selectedLabel} 예시` : '통합 예시'

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
          placeholder="국회 상임위원회 회의록 전체에서 검색"
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
      <div className="search-filter-bar">
        <button
          type="button"
          className={`filter-toggle${filterOpen ? ' filter-toggle--active' : ''}`}
          onClick={() => setFilterOpen(open => !open)}
          aria-expanded={filterOpen}
          disabled={loading}
        >
          상세 필터
        </button>
        <span className={`filter-status${selectedCommittee ? ' filter-status--active' : ''}`}>
          {selectedCommittee ? `${selectedLabel}만 검색` : '전체 자동 검색'}
        </span>
        {selectedCommittee && (
          <button
            type="button"
            className="filter-clear"
            onClick={() => onCommitteeChange(null)}
            disabled={loading}
          >
            초기화
          </button>
        )}
      </div>
      {filterOpen && (
        <div className="advanced-filter-panel">
          <div className="filter-section">
            <p className="filter-section-label">위원회</p>
            <div className="committee-filter-options" role="group" aria-label="위원회 필터">
              {QUESTION_COMMITTEE_FILTERS.map(c => (
                <button
                  key={String(c.value)}
                  type="button"
                  className={`filter-pill${selectedCommittee === c.value ? ' filter-pill--active' : ''}`}
                  onClick={() => onCommitteeChange(c.value)}
                  disabled={loading}
                >
                  {c.label}
                </button>
              ))}
            </div>
            <p className="filter-helper">
              선택하지 않으면 질문과 가장 관련 높은 회의록을 전체 위원회에서 찾습니다.
            </p>
          </div>
        </div>
      )}
      <div className="example-chips">
        <span className="example-label">{exampleLabel}</span>
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
