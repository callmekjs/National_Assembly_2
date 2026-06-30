export function formatCitationSpeaker(citation = {}) {
  const speaker = String(citation.speaker || '').trim()
  const role = String(citation.speaker_role || '').trim()

  if (!speaker && !role) return '미상'
  if (!speaker) return role
  if (!role) return speaker
  if (speaker.includes(role) || role.includes(speaker)) return speaker
  if (speaker === '후보자' || speaker === '공직후보자') return `${role} ${speaker}`
  return `${speaker} ${role}`
}
