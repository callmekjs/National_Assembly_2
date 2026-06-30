import { useEffect, useRef } from 'react'
import { formatCitationSpeaker } from './citationDisplay'
import { buildPdfSrc } from './pdfUrls'

export default function PdfViewerPanel({ citation, onClose }) {
  const pdfSrc = buildPdfSrc(citation)
  const speakerLabel = formatCitationSpeaker(citation)
  const panelRef = useRef(null)
  const closeButtonRef = useRef(null)

  useEffect(() => {
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow

    document.body.style.overflow = 'hidden'
    closeButtonRef.current?.focus()

    return () => {
      document.body.style.overflow = previousOverflow
      if (previousFocus instanceof HTMLElement) {
        previousFocus.focus()
      }
    }
  }, [])

  function handleKeyDown(e) {
    if (e.key !== 'Tab') return

    const focusable = panelRef.current?.querySelectorAll(
      'button, [href], input, select, textarea, iframe, [tabindex]:not([tabindex="-1"])',
    )
    const focusableItems = Array.from(focusable || []).filter(el => !el.disabled)
    if (!focusableItems.length) return

    const first = focusableItems[0]
    const last = focusableItems[focusableItems.length - 1]

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <aside
      className="pdf-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pdf-panel-title"
      tabIndex={-1}
      ref={panelRef}
      onKeyDown={handleKeyDown}
    >
      <div className="pdf-panel-header">
        <h2 id="pdf-panel-title">원문 근거 보기</h2>
        <button
          type="button"
          className="pdf-panel-close"
          onClick={onClose}
          aria-label="닫기"
          ref={closeButtonRef}
        >
          ×
        </button>
      </div>

      <dl className="pdf-panel-meta">
        <div className="pdf-meta-row">
          <dt>회의일</dt>
          <dd>{citation.date || '-'}</dd>
        </div>
        <div className="pdf-meta-row">
          <dt>발언자/직책</dt>
          <dd>
            {speakerLabel}
            {citation.speaker_original && citation.speaker_original !== citation.speaker && (
              <span className="speaker-original">원문 {citation.speaker_original}</span>
            )}
          </dd>
        </div>
        <div className="pdf-meta-row">
          <dt>근거 번호</dt>
          <dd>[{citation.index}]</dd>
        </div>
        <div className="pdf-meta-row pdf-meta-row--full">
          <dt>내용 미리보기</dt>
          <dd>{citation.content_preview || '-'}</dd>
        </div>
      </dl>

      {pdfSrc ? (
        <div className="pdf-panel-viewer">
          <iframe
            title={`회의록 PDF - 근거 ${citation.index}`}
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
