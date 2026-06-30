export const QUESTION_COMMITTEE_FILTERS = [
  { label: '전체 자동', value: null },
  { label: '외교통일', value: '외교통일위원회' },
  { label: '정무', value: '정무위원회' },
  { label: '과기정통', value: '과학기술정보방송통신위원회' },
]

export const EXAMPLE_QUESTIONS_BY_COMMITTEE = {
  null: [
    '강제동원 피해자 배상 관련 질의 정리해줘',
    '금융위원장 은행 금리 규제에 대한 입장은?',
    'SKT 유심 해킹 사태에 대한 국회 논의는?',
    'AI 반도체 예산 논의가 있었어?',
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

export const FEATURES = [
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

export const UTTERANCE_COLORS = {
  question: '#2563eb',
  answer: '#16a34a',
  statement: '#6b7280',
  procedural: '#d1d5db',
}

export const PARTY_COLORS = {
  '더불어민주당': '#1a56db',
  '국민의힘': '#e8230a',
  '조국혁신당': '#7c3aed',
}

export const COMMITTEE_SHORT = {
  '외교통일위원회': '외교통일',
  '과학기술정보방송통신위원회': '과기정통',
  '정무위원회': '정무',
}

export const MEETING_COMMITTEE_FILTERS = [
  '외교통일위원회',
  '정무위원회',
  '과학기술정보방송통신위원회',
]

export const MEETING_YEAR_FILTERS = ['2024', '2025', '2026']

export const CORE_TIMELINE_LIMIT = 16
export const CORE_QA_LIMIT = 8
export const CORE_QA_CONFIDENCE = 0.6
export const ISSUE_SCORE_LIMIT = 4

export const ISSUE_LABEL_RULES = [
  { title: '투명성 센터 설치와 운영 공백', keywords: ['투명성 센터', '투명성센터'] },
  { title: '방송미디어통신진흥원 설립 및 법안 처리', keywords: ['방송미디어통신진흥원', '진흥원', '정보통신망법'] },
  { title: '가맹사업법 안건 처리와 의사일정 변경', keywords: ['가맹사업법', '가맹사업'] },
  { title: '법안 심사 방식과 안건 분리', keywords: ['전부개정안', '각각 안건', '안건이 논의', '법안은 전부개정안'] },
  { title: '예산 편성·집행 및 삭감 근거', keywords: ['예산', '삭감', '증액', '감액', '집행'] },
  { title: '대북 정책과 남북관계 대응', keywords: ['대북', '북한', '남북', '통일'] },
  { title: '금융 규제와 시장 감독', keywords: ['금융', '은행', '금리', '공정거래', '감독'] },
  { title: '방송·통신 정책과 기관 운영', keywords: ['방송', '통신', '미디어', '방통'] },
]

export const GOV_ROLE_PATTERN = /(정부|장관|차관|위원장|부위원장|실장|원장|청장|처장|전문위원)/
