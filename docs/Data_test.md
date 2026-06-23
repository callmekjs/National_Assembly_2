# 데이터 파이프라인 테스트 명세서

> 관점: GovTech 10년차 CTO  
> 원칙: 파이프라인이 조용히 실패하는 것이 가장 위험하다. 각 단계 출력이 다음 단계의 입력 품질을 보장해야 한다.  
> 전제: ETL은 이미 1회 완료된 상태. 이 테스트는 현재 산출물의 건전성을 점검한다.

---

## D-1. 중간 산출물 존재 확인

### D-1-1. Extract 산출물
**방법**:
```bash
python -c "
from pathlib import Path
p = Path('data/extract/extracted.jsonl')
lines = [l for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
print(f'extracted.jsonl: {len(lines)}건')
"
```
**PASS 기준**: 50건 이상 (55건 PDF 기준)

---

### D-1-2. Normalize 산출물
**방법**:
```bash
python -c "
from pathlib import Path
p = Path('data/transform/normalized/normalized.jsonl')
lines = [l for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
print(f'normalized.jsonl: {len(lines)}건')
"
```
**PASS 기준**: extracted.jsonl 건수와 동일

---

### D-1-3. Chunk 산출물
**방법**:
```bash
python -c "
from pathlib import Path
p = Path('data/transform/final/chunks.jsonl')
lines = [l for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
print(f'chunks.jsonl: {len(lines)}건')
"
```
**PASS 기준**: 15,000건 이상 (DB의 chunks 테이블과 ±100 이내)

---

## D-2. Contract 검증

### D-2-1. 전체 파이프라인 Contract 통과
**방법**:
```bash
python -m service.etl.contract
```
**PASS 기준**:
- `[contract] 전체 검증 통과 ✓` 출력
- errors=0 (REQUIRED 필드 누락 없음)

---

### D-2-2. 청크 필수 필드 누락 없음
**방법**: D-2-1 결과의 `[contract:chunk]` 섹션 확인  
**PASS 기준**:
- `REQ:chunk_id` fill=100%
- `REQ:content` fill=100%

---

## D-3. 품질 리포트

### D-3-1. Quality 리포트 실행
**방법**:
```bash
python -m service.etl.quality
```
**PASS 기준**: `data/reports/quality_*.json` 생성, 오류 없음

---

### D-3-2. 청크 크기 분포
**방법**: D-3-1 결과 확인  
**PASS 기준**:
- avg 길이 200자 이상
- 300자 미만 비율 < 30%
- max 길이 5,000자 미만 (너무 큰 청크는 LLM 토큰 낭비)

---

### D-3-3. 메타데이터 채움률
**방법**: D-3-1 결과의 fill_rate 확인  
**PASS 기준**:
- speaker fill ≥ 90%
- committee fill = 100%
- meeting_date fill = 100%

---

### D-3-4. 짧은 청크 비율
**방법**: D-3-1 결과의 short_chunk 확인  
**PASS 기준**:
- 80자 미만 비율 < 5%

---

## D-4. 발언자 추출 정확도 (샘플 검증)

### D-4-1. 발언자 형식 확인
**방법**:
```bash
python -c "
import psycopg2, json
conn = psycopg2.connect(host='localhost', port=5433, database='skn_project', user='postgres', password='post1234')
cur = conn.cursor()
cur.execute(\"\"\"
    SELECT metadata->>'speaker', COUNT(*) as cnt
    FROM chunks
    GROUP BY metadata->>'speaker'
    ORDER BY cnt DESC
    LIMIT 15
\"\"\")
for row in cur.fetchall():
    print(f'{row[1]:5d}건  {row[0]}')
conn.close()
"
```
**PASS 기준**:
- 상위 발언자가 "직함+이름" 또는 "이름" 형식
- "발언자 미상", None, 빈 문자열이 상위 5위 안에 없음
- 외교부장관·통일부장관 포함 확인

---

### D-4-2. 발언자-청크 내용 일치 샘플 검증
**방법**:
```bash
python -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, database='skn_project', user='postgres', password='post1234')
cur = conn.cursor()
cur.execute(\"\"\"
    SELECT metadata->>'speaker', LEFT(text, 200)
    FROM chunks
    WHERE metadata->>'speaker' LIKE '%조태열%'
    LIMIT 3
\"\"\")
for row in cur.fetchall():
    print(f'[발언자] {row[0]}')
    print(f'[내용]   {row[1]}')
    print('---')
conn.close()
"
```
**PASS 기준**:
- 청크 내용이 해당 발언자의 실제 발언으로 시작 (타 발언자 내용 없음)
- "○ 조태열" 또는 발언자 마커 이후 내용만 포함

---

## D-5. 추적성 (Traceability)

### D-5-1. 청크 → PDF 소스 역추적
**방법**:
```bash
python -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, database='skn_project', user='postgres', password='post1234')
cur = conn.cursor()
cur.execute(\"\"\"
    SELECT chunk_id, metadata->>'source_path', metadata->>'meeting_date', metadata->>'speaker'
    FROM chunks
    LIMIT 5
\"\"\")
for row in cur.fetchall():
    print(f'chunk_id:    {row[0]}')
    print(f'source_path: {row[1]}')
    print(f'date:        {row[2]}')
    print(f'speaker:     {row[3]}')
    print('---')
conn.close()
"
```
**PASS 기준**:
- 모든 청크에 source_path 존재
- source_path가 실제 존재하는 PDF 경로

---

### D-5-2. Run History 기록 확인
**방법**:
```bash
python -c "
from pathlib import Path
import json
p = Path('data/reports/run_history.jsonl')
lines = [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
print(f'총 실행 이력: {len(lines)}건')
last = lines[-1]
print(f'최근 run_id: {last[\"run_id\"]}')
print(f'시작 시각:   {last[\"started_at\"]}')
print(f'contract:    {last.get(\"contract_ok\")}')
"
```
**PASS 기준**:
- 실행 이력 1건 이상
- 최근 이력의 contract_ok = True

---

## D-6. Incremental 임베딩

### D-6-1. 중복 임베딩 방지 확인
**방법**:
```bash
python -m service.etl.loader.loader_cli load vector --dry-run
```
*(dry-run 옵션 없으면 아래로 대체)*
```bash
python -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5433, database='skn_project', user='postgres', password='post1234')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM embeddings_e5')
before = cur.fetchone()[0]
# chunk_id 중복 여부
cur.execute('SELECT COUNT(DISTINCT chunk_id) FROM embeddings_e5')
distinct = cur.fetchone()[0]
print(f'전체 임베딩: {before}건')
print(f'고유 chunk_id: {distinct}건')
print(f'중복: {before - distinct}건')
conn.close()
"
```
**PASS 기준**:
- 전체 임베딩 수 = 고유 chunk_id 수 (중복 0건)

---

## 테스트 통과 기준 요약

| ID | 항목 | 필수 |
|----|------|------|
| D-1-1 | extracted.jsonl 존재 및 건수 | ✅ 필수 |
| D-1-2 | normalized.jsonl 존재 및 건수 | ✅ 필수 |
| D-1-3 | chunks.jsonl 존재 및 건수 | ✅ 필수 |
| D-2-1 | Contract 전체 통과 | ✅ 필수 |
| D-2-2 | 청크 필수 필드 누락 없음 | ✅ 필수 |
| D-3-1 | Quality 리포트 생성 | ✅ 필수 |
| D-3-2 | 청크 크기 분포 | ✅ 필수 |
| D-3-3 | 메타데이터 채움률 | ✅ 필수 |
| D-3-4 | 짧은 청크 비율 | ✅ 필수 |
| D-4-1 | 발언자 형식 확인 | ✅ 필수 |
| D-4-2 | 발언자-내용 일치 샘플 검증 | ✅ 필수 |
| D-5-1 | 청크 → PDF 역추적 | ✅ 필수 |
| D-5-2 | Run History 기록 | 권장 |
| D-6-1 | 중복 임베딩 방지 | ✅ 필수 |

**13개 필수 항목 전부 PASS → 데이터 레이어 건전성 확인 완료**
