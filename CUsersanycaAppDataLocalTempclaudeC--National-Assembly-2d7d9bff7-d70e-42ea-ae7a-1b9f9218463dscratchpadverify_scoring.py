# Verify scoring logic against spec
from service.rag.query.question_types import infer_importance_score

# Test case 1: zero for procedural (no commitment match)
score1 = infer_importance_score("오늘 회의를 개의하겠습니다.")
print(f"1. Procedural (no commitment): {score1} == 0.0? {score1 == 0.0}")

# Test case 2: commitment signals (2 matches × 0.15 = 0.30)
score2 = infer_importance_score("조속히 검토하겠습니다. 시행하겠습니다.")
print(f"2. Commitment (2×0.15=0.30): {score2} >= 0.15? {score2 >= 0.15}")

# Test case 3: decision marker (+0.20)
score3 = infer_importance_score("정부 입장을 말씀드리겠습니다.")
print(f"3. Decision marker: {score3} >= 0.20? {score3 >= 0.20}")

# Test case 4: govt answer bonus
base4 = infer_importance_score("노력하겠습니다.", utterance_type="statement", position_type="의원")
boosted4 = infer_importance_score("노력하겠습니다.", utterance_type="answer", position_type="정부측")
print(f"4. Govt answer bonus: base={base4}, boosted={boosted4}, boosted>base? {boosted4 > base4}")
print(f"   Expected: base=0.15 (1 commit × 0.15), boosted=0.35 (0.15+0.20)")

# Test case 5: Capped at 1.0
text5 = "시행하겠습니다. 추진하겠습니다. 마련하겠습니다. 정부 입장을 밝힙니다. 장관으로서 공식적으로 답변드립니다."
score5 = infer_importance_score(text5, utterance_type="answer", position_type="정부측")
print(f"5. Capped at 1.0: {score5} == 1.0? {score5 == 1.0}")
print(f"   Components: 3 commits(0.45) + decision(0.20) + formal(0.15) + govt_bonus(0.20) = 1.0")

# Test case 6: member question bonus
base6 = infer_importance_score("정부 입장은?", utterance_type="statement", position_type="기타")
boosted6 = infer_importance_score("정부 입장은?", utterance_type="question", position_type="의원")
print(f"6. Member question bonus: base={base6}, boosted={boosted6}, boosted>base? {boosted6 > base6}")
print(f"   Expected: base=0.20 (decision), boosted=0.30 (0.20+0.10)")

# Verify pattern names
import re
from service.rag.query.question_types import (
    _IMPORTANCE_COMMITMENT, _IMPORTANCE_DECISION, _IMPORTANCE_FORMAL
)
print(f"\n7. Pattern names validation:")
print(f"   _IMPORTANCE_COMMITMENT exists? {_IMPORTANCE_COMMITMENT is not None}")
print(f"   _IMPORTANCE_DECISION exists? {_IMPORTANCE_DECISION is not None}")
print(f"   _IMPORTANCE_FORMAL exists? {_IMPORTANCE_FORMAL is not None}")

# Check pattern examples
print(f"\n8. Pattern matching examples:")
print(f"   Commitment '검토하겠습니다': {bool(_IMPORTANCE_COMMITMENT.search('검토하겠습니다'))}")
print(f"   Decision '정부 입장': {bool(_IMPORTANCE_DECISION.search('정부 입장'))}")
print(f"   Formal '장관으로서': {bool(_IMPORTANCE_FORMAL.search('장관으로서'))}")
