# Task 2 Report: normalizer_v2.py — 잡음 제거 + section_type 분류

## Status
**DONE**

## Files Created
- `service/etl/transform/normalizer_v2.py` — 78 lines (66 non-empty)
- `tests/test_normalizer_v2.py` — 64 lines (40 non-empty)

## Test Results
```
pytest tests/test_normalizer_v2.py -v
============================= test session starts =============================
collected 11 items

test_classify_body_with_speaker_marker PASSED       [  9%]
test_classify_agenda PASSED                         [ 18%]
test_classify_cover PASSED                          [ 27%]
test_classify_appendix PASSED                       [ 36%]
test_classify_body_default PASSED                   [ 45%]
test_clean_removes_standalone_page_number PASSED    [ 54%]
test_clean_fixes_korean_word_split PASSED           [ 63%]
test_clean_removes_dot_leader PASSED                [ 72%]
test_clean_removes_committee_header PASSED          [ 81%]
test_clean_removes_national_assembly_footer PASSED  [ 90%]
test_clean_removes_session_header PASSED            [100%]

============================== 11 passed in 0.02s ==============================
```

## Implementation Summary

### clean_text(raw: str) → str
Removes noise from raw text:
1. Removes null bytes and BOM characters
2. Removes zero-width Unicode characters
3. Removes committee meeting headers
4. Filters out noise lines (page numbers, decorators, session headers)
5. Fixes Korean word-split across line boundaries (e.g., "교\n류" → "교류")
6. Normalizes whitespace and collapses excessive newlines

**Key noise patterns filtered:**
- Session headers (e.g., "제416회-외교통일제1차(임시회)")
- National Assembly footer (e.g., "국 회 사 무 처")
- Committee meeting headers (e.g., "외교통일위원회회의록")
- Standalone page numbers
- Dot-leader lines (e.g., "........ 12")

### classify_section(raw_text: str) → str
Classifies text into four section types:
- **cover**: Contains "국 회 사 무 처" (National Assembly header)
- **agenda**: Contains agenda markers (의사일정, 상정된안건, etc.)
- **appendix**: Contains appendix markers (보고사항, 붙임, 이상입니다)
- **body**: Default/contains speaker markers (◯) or anything else

## Self-Review

### Implementation Quality
- Follows exact interface specification from brief
- Robust regex patterns handle Korean text with spacing variations
- Proper error handling for empty/None inputs
- All noise filtering patterns cover documented cases

### Process Issue & Resolution
The brief's provided implementation had a subtle bug: Korean word-merging happened BEFORE noise filtering, which allowed noise phrases to survive if they were merged with surrounding text. 

**Fix applied:** Reordered operations to filter noise lines BEFORE merging broken words. This ensures:
1. Noise patterns are matched against complete, individual lines
2. Once matched, lines are removed before the merging step
3. No noise phrases can be resurrected through character merging

This reordering is necessary to make all test cases pass without modifying the test specifications.

### Test Coverage
- Classified 5 section types correctly (body with speaker, agenda, cover, appendix, default body)
- Noise removal 6 types (standalone page numbers, Korean word splits, dot-leaders, committee headers, footers, session headers)
- Total: 11 passing tests covering all public APIs

## Commits
```
5b061af feat: normalizer_v2 — 잡음 제거 + section_type 분류
```

## Next Steps
Task 3: parser_v2.py — speaker turn 구조화 (ready to start)

Input: `data/v2/transform/normalized_v2.jsonl` (from this task)
Output: `data/v2/parse/parsed_v2.jsonl`
