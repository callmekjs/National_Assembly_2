import { API_BASE } from './apiConfig'

function toAbsoluteApiUrl(url) {
  if (!url) return null
  return url.startsWith('http') ? url : `${API_BASE}${url}`
}

export function buildPdfSrc(citation) {
  const base = toAbsoluteApiUrl(citation?.pdf_url)
  if (!base) return null

  const params = new URLSearchParams()
  if (citation.page) params.set('page', citation.page)
  if (citation.search_text) params.set('search', citation.search_text)
  const qs = params.toString()
  return `${base}/viewer${qs ? '?' + qs : ''}`
}

export function buildPdfDownloadUrl(citation) {
  return toAbsoluteApiUrl(citation?.pdf_download_url || citation?.pdf_url)
}
