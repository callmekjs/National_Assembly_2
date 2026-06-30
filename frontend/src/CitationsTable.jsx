import { COMMITTEE_SHORT } from './appConstants'
import { formatCitationSpeaker } from './citationDisplay'
import { buildPdfDownloadUrl } from './pdfUrls'

function citationSortLabel(sort) {
  const map = {
    chronological: '회의일순',
    relevance: '관련도순',
  }
  return map[sort] || map.relevance
}

export default function CitationsTable({ citations, citationSort, selectedCitation, onSelect }) {
  return (
    <div className="citations">
      <div className="citations-heading">
        <h4 className="citations-title">참고 자료</h4>
        <span className="citation-sort-badge">{citationSortLabel(citationSort)}</span>
      </div>
      <p className="citations-hint">내용을 누르면 원문 viewer가 열리고, 파일 저장은 다운로드 버튼을 사용합니다.</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>위원회</th>
              <th>회의일</th>
              <th>발언자/직책</th>
              <th>내용</th>
              <th>파일</th>
            </tr>
          </thead>
          <tbody>
            {citations.map(c => {
              const isSelected = selectedCitation?.index === c.index
                && selectedCitation?.content_preview === c.content_preview
              const downloadUrl = buildPdfDownloadUrl(c)
              const speakerLabel = formatCitationSpeaker(c)
              return (
                <tr
                  key={c.index}
                  className={`citation-row${isSelected ? ' citation-row--selected' : ''}`}
                >
                  <td className="col-index">{c.index}</td>
                  <td className="col-committee">
                    {c.committee ? (
                      <span className="committee-badge">{COMMITTEE_SHORT[c.committee] || c.committee}</span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="col-date">{c.date || '—'}</td>
                  <td className="col-speaker">
                    <span>{speakerLabel}</span>
                    {c.speaker_original && c.speaker_original !== c.speaker && (
                      <span className="speaker-original">원문 {c.speaker_original}</span>
                    )}
                  </td>
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
