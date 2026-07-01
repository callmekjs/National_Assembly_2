import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(1, 1, figsize=(22, 14))
ax.set_xlim(0, 22)
ax.set_ylim(0, 14)
ax.axis('off')
fig.patch.set_facecolor('#FAFAF7')

# 한글 폰트
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

# ── 제목 ──────────────────────────────────────────────
ax.text(11, 13.3, '〈 국회 회의록 RAG — 서비스 개발 전체 과정 〉',
        ha='center', va='center', fontsize=18, fontweight='bold', color='#222')

# ── 색상 정의 ─────────────────────────────────────────
COLORS = {
    '기획':    '#A8D8A8',   # 연두
    '설계':    '#F7E08A',   # 노랑
    '개발':    '#A8C8E8',   # 파랑
    '소스관리': '#F4A8B8',  # 핑크
    '배포':    '#F4C890',   # 주황
    '출시':    '#C8A8E8',   # 보라
    '유지보수': '#F4A88A',  # 연분홍
}

# ── 단계 원형 노드 위치 ───────────────────────────────
nodes = [
    ('기획',    1.5, 11.5),
    ('설계',    4.0, 11.5),
    ('개발',    6.8, 11.5),
    ('소스관리', 11.5, 11.5),
    ('배포',    14.5, 11.5),
    ('출시',    17.5, 11.5),
    ('유지보수', 20.5, 11.5),
]

# 원형 노드 그리기
for label, x, y in nodes:
    color = COLORS[label]
    circle = plt.Circle((x, y), 0.75, color=color, zorder=3, linewidth=2, edgecolor='white')
    ax.add_patch(circle)
    ax.text(x, y, label, ha='center', va='center', fontsize=12,
            fontweight='bold', color='#222', zorder=4)

# 화살표 연결
arrow_pairs = [
    (1.5, 4.0), (4.0, 6.05), (6.8, 10.75),
    (11.5, 13.75), (14.5, 16.75), (17.5, 19.75)
]
for x1, x2 in arrow_pairs:
    ax.annotate('', xy=(x2 - 0.75, 11.5), xytext=(x1 + 0.75, 11.5),
                arrowprops=dict(arrowstyle='->', color='#555', lw=2))

# 개발에서 아래로 화살표
ax.annotate('', xy=(6.8, 10.2), xytext=(6.8, 10.75),
            arrowprops=dict(arrowstyle='->', color='#555', lw=2))

# ── 상세 내용 박스 ────────────────────────────────────
def draw_box(ax, x, y, width, height, color, title, lines, title_color='#222', check=None):
    box = FancyBboxPatch((x, y), width, height,
                         boxstyle="round,pad=0.1",
                         facecolor=color, edgecolor='#ccc', linewidth=1.2, zorder=2)
    ax.add_patch(box)
    # 제목
    icon = '[완료]' if check == 'ok' else ('[절반]' if check == 'half' else ('[미완]' if check == 'no' else ''))
    ax.text(x + width/2, y + height - 0.3, f'{icon} {title}',
            ha='center', va='top', fontsize=10, fontweight='bold', color=title_color)
    # 내용
    for i, line in enumerate(lines):
        ax.text(x + 0.15, y + height - 0.65 - i*0.42,
                line, ha='left', va='top', fontsize=8.5, color='#333')

# [기획] ✅
draw_box(ax, 0.1, 7.5, 3.0, 3.5, '#E8F5E8', '기획', [
    '· MVP: 회의록 질문-답변 시스템',
    '· 타겟: 회의록 검색·분석 사용자',
    '· 핵심기능: 발언자 귀속, 근거 인용',
    '· 위원회별 검색 (외통위·정무위·과방위)',
    '· (경쟁분석·차별화 전략 생략)',
], check='ok')

# [설계] ✅
draw_box(ax, 3.3, 7.5, 2.8, 3.5, '#FEF9E0', '설계', [
    '· DB: chunks_v2, embeddings_e5_v2',
    '· PostgreSQL + pgvector',
    '· API: /query, /health, /meetings',
    '· FastAPI 엔드포인트 설계',
    '· (화면설계 최소화)',
], check='ok')

# [개발] ✅ — 3개 서브박스
draw_box(ax, 5.3, 3.5, 4.2, 6.6, '#E0EEF8', '개발', [], check='ok')

# 프론트엔드 서브
draw_box(ax, 5.5, 7.8, 3.8, 2.1, '#C8DFF4', '[프론트엔드]', [
    '· React (Vite)',
    '· Chat UI + PDF 뷰어',
    '· SSE 스트리밍',
], title_color='#1a5276')

# 백엔드 서브
draw_box(ax, 5.5, 5.5, 3.8, 2.1, '#C8DFF4', '[백엔드]', [
    '· FastAPI + LangGraph 파이프라인',
    '· Router→Retrieve→Rerank',
    '· →Generate→GroundingCheck',
], title_color='#1a5276')

# DB 서브
draw_box(ax, 5.5, 3.7, 3.8, 1.6, '#F7E08A', '[DB 구축]', [
    '· ETL 파이프라인 (7단계)',
    '· 78,952행 로드 / 3개 위원회',
], title_color='#7D6608')

# [소스관리] ✅
draw_box(ax, 10.1, 7.5, 2.8, 3.5, '#FCE4EC', '소스관리', [
    '· GitHub',
    '· callmekjs/National_Assembly_2',
    '· main 브랜치 단일 운영',
    '· 커밋 50+회',
], check='ok')

# [배포] 🔺
draw_box(ax, 13.2, 7.5, 2.8, 3.5, '#FFF3E0', '배포', [
    '· 프론트: Vercel [완료]',
    '  national-assembly-2.vercel.app',
    '· 백엔드: 미배포 [미완]',
    '  (BGE-M3 2.2GB → RAM 부족)',
], check='half')

# [출시] ❌
draw_box(ax, 16.2, 7.5, 2.8, 3.5, '#EDE7F6', '출시', [
    '· Vercel 자동 HTTPS만 적용',
    '· 커스텀 도메인 없음',
    '· App Store 등록 없음',
    '· 백엔드 미배포로 미완성',
], check='no')

# [유지보수] ✅
draw_box(ax, 19.2, 7.5, 2.7, 3.5, '#FBE9E7', '유지보수', [
    '· eval 75문항 성능 추적',
    '· 88% 달성 (66/75)',
    '· 단위 테스트 111개',
    '· 버그 수정 이력 Git 관리',
], check='ok')

# ── 하단 요약 박스 ─────────────────────────────────────
summary_box = FancyBboxPatch((0.5, 0.3), 21, 2.8,
                              boxstyle="round,pad=0.15",
                              facecolor='#F0F4FF', edgecolor='#8899CC', linewidth=1.5)
ax.add_patch(summary_box)
ax.text(11, 2.85, '[ 프로토타입 핵심 성과 및 포트폴리오 과제 ]',
        ha='center', va='center', fontsize=11, fontweight='bold', color='#1a237e')

summary_lines = [
    '[완료] ETL 파이프라인 7단계  |  하이브리드 검색(BM25+벡터 RRF)  |  LangGraph RAG 파이프라인  |  Grounding Check  |  eval 88%  |  Vercel 배포',
    '[한계] BGE-M3 로컬 모델(2.2GB) → 백엔드 무료 배포 불가  |  로그인/회원가입 없음  |  도메인 없음',
    '[포트폴리오] OpenAI Embedding API로 경량화 → 전체 배포  |  로그인  |  도메인  |  완성도 높은 UI',
]
for i, line in enumerate(summary_lines):
    ax.text(1.0, 2.35 - i * 0.65, line, ha='left', va='top', fontsize=9, color='#222')

plt.tight_layout(pad=0.5)
plt.savefig(r'C:\National_Assembly_2\스크린샷\개발과정.jpg',
            dpi=150, bbox_inches='tight', facecolor='#FAFAF7')
print('저장 완료')
