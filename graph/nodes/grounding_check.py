"""
GroundingCheck 노드

완료 기준:
  1) 답변 주요 주장마다 [n] 붙음 — 미인용 문장은 ## 확인된 범위로 이동
  2) [n]이 실제 검색 결과 범위 안에 있음 — 범위 밖은 [?]로 교체
  3) 인용한 청크가 주장을 뒷받침함 — 키워드 오버랩 휴리스틱 체크
  4) 근거 없는 문장은 ## 확인된 범위로 이동
  5) 검색 결과가 약하면 답변 생성 거부 (MIN_DOCS / WEAK_SCORE 임계값)
  6) 정답 없는 질문 → 무리한 답변 없음 (테스트: unanswerable_eval.py)

grounding_level:
  FULL    (score > 0.6) : 인용 충분
  PARTIAL (0 < score ≤ 0.6) : 일부 미인용 — 미인용 문장 확인된 범위로 이동
  NONE    (score == 0)  : 인용 없음 — 경고 또는 약한 검색 시 답변 거부
"""
from __future__ import annotations

import re

from graph.state import QAState

# ── 임계값 ────────────────────────────────────────────────────────
CITE_FULL_THRESHOLD   = 0.6   # 이 이상이면 FULL
MIN_DOCS_FOR_ANSWER   = 2     # 최소 문서 수 (미만이면 weak)
WEAK_SCORE_THRESHOLD  = 0.35  # 최고 rerank_score 미만이면 weak

# ── 경고 문구 ─────────────────────────────────────────────────────
_WARN_PARTIAL = (
    "\n\n*ℹ 일부 주장에 인용 번호(`[n]`)가 없습니다. "
    "아래 참고 자료를 직접 검토하세요.*"
)
_WARN_SPEAKER_MISMATCH = (
    "\n\n*⚠ 일부 세부 근거의 출처 발언자가 주장 인물과 일치하지 않아 확인된 범위로 이동했습니다. "
    "참고 자료의 실제 발언자를 직접 확인하세요.*"
)
_WARN_NONE = (
    "\n\n*⚠ 이 답변은 검색된 회의록에서 직접 인용 번호(`[n]`)를 확인하지 못했습니다. "
    "내용이 회의록 근거와 다를 수 있으니 참고 자료를 직접 확인하세요.*"
)
_REFUSAL_WEAK = (
    "검색된 회의록 자료가 부족하거나 관련도가 낮아 "
    "신뢰할 수 있는 답변을 생성하기 어렵습니다.\n\n"
    "더 구체적인 질문이나 다른 표현으로 다시 질문해 주세요."
)

# ── 줄 필터 패턴 ─────────────────────────────────────────────────
# 점수 계산·미인용 이동에서 제외할 줄 (헤더, 블록쿼트, 마커, 빈 줄)
# 주의: `- **발언자**` 형태 볼드 불릿은 제외하지 않음 (인용 번호가 달릴 수 있음)
_SKIP = re.compile(r"^(#{1,4}\s|>\s|\*[^*]|\s*$)")

# 핵심 결론에서 "확인 불가" 판단 패턴
_CONCLUSION_REFUSAL = re.compile(
    r"확인되지 않|확인할 수 없|찾지 못했|찾을 수 없|확인되지 않았|없습니다\.$"
)

# 발언자에서 직함·부처명 판단 (이름 추출 시 제외)
_NON_NAME_WORDS = re.compile(
    r"통일부|외교부|국방부|기획재정부|환경부|산업부|과기부|행안부|문체부|농림부|복지부|"
    r"여가부|법무부|국토부|해수부|교육부|고용부|"
    r"장관|의원|위원장|위원|차관|총장|원장|대표|의장|부장관"
)

# 세부 근거 불릿의 볼드 발언자 파싱 ("- **발언자**: ...")
_BULLET_BOLD_RE = re.compile(r"^(-\s*\*\*)(.+?)(\*\*)(.*)", re.DOTALL)

# 비교 쿼리 한계 섹션 정리: "찾을 수 없" 또는 "비교 근거 부족" 패턴
_COMP_MISSING_RE = re.compile(r"찾을\s*수\s*없|비교\s*근거\s*부족")
_MAIN_HEADER_RE = re.compile(r"#{1,4}\s*(?:핵심\s*결론|메인\s*결과)")


# ── 유틸 ─────────────────────────────────────────────────────────

def _extract_conclusion_text(ans: str) -> str:
    """메인 결과/핵심 결론 섹션 텍스트만 추출. 헤더와 같은 줄에 붙은 내용도 포함."""
    lines = ans.splitlines()
    in_conclusion = False
    buf: list[str] = []
    for line in lines:
        s = line.strip()
        m = re.match(r"#{1,4}\s*(?:핵심\s*결론|메인\s*결과)\s*(.*)", s)
        if m:
            in_conclusion = True
            inline = m.group(1).strip()
            if inline:
                buf.append(inline)
            continue
        if in_conclusion:
            if s.startswith("## "):
                break
            buf.append(s)
    return " ".join(buf)


def _strip_detail_if_conclusion_refusal(ans: str) -> tuple[str, bool]:
    """
    핵심 결론이 순수 거부(비어있거나 인용 없이 확인 불가)일 때만 세부 근거 제거.
    결론에 [n] 인용이 있으면 실제 데이터가 있는 것 → 세부 근거 유지.
    반환: (수정된 답변, 제거 여부)
    """
    conclusion = _extract_conclusion_text(ans)
    # 결론에 [n] 인용이 있으면 실제 데이터가 있는 것 → 세부 근거 유지
    if conclusion and re.search(r"\[\d+\]", conclusion):
        return ans, False
    # 결론 내용이 있고 거부 패턴도 없으면 → 유지
    if conclusion and not _CONCLUSION_REFUSAL.search(conclusion):
        return ans, False

    lines = ans.splitlines()
    result: list[str] = []
    in_detail = False
    for line in lines:
        s = line.strip()
        if re.match(r"#{1,4}\s*세부\s*근거", s):
            in_detail = True
            continue
        if in_detail:
            if s.startswith("## "):
                in_detail = False
            else:
                continue
        if not in_detail:
            result.append(line)

    return "\n".join(result), True


def _extract_personal_names(text: str) -> set[str]:
    """발언자 표현에서 직함·부처명을 제외한 이름 토큰 추출 (2-4 글자 한글)."""
    return {t for t in re.findall(r"[가-힣]{2,4}", text) if not _NON_NAME_WORDS.search(t)}


def _speaker_name_matches(stated: str, actual: str) -> bool:
    """두 발언자 표현이 같은 사람인지 개인 이름 오버랩으로 판단.
    둘 중 하나라도 이름이 없으면(직함·부처만) 교정 불필요로 간주.
    """
    s_names = _extract_personal_names(stated)
    a_names = _extract_personal_names(actual)
    if s_names and a_names:
        return bool(s_names & a_names)
    return True


def _speaker_from_text(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    m = re.search(r"\[발언자:\s*([^\]\n]+)\]", t)
    if m:
        return m.group(1).strip()
    m = re.match(r"[○◯]\s*([가-힣A-Za-z0-9·ㆍ-]{2,20}(?:\s+[가-힣A-Za-z0-9·ㆍ-]{1,20})?)", t)
    return m.group(1).strip() if m else ""


def _doc_speaker_label(doc: dict) -> str:
    meta = doc.get("metadata") or {}
    speaker = str(doc.get("speaker") or meta.get("speaker") or "").strip()
    role = str(doc.get("speaker_role") or meta.get("speaker_role") or "").strip()
    if not speaker:
        speaker = _speaker_from_text(doc.get("chunk_text", "") or doc.get("content", ""))
    if speaker and role and role not in speaker:
        return f"{speaker} {role}"
    return speaker or role


def _get_chunk_speaker(docs: list[dict], n: int) -> str:
    """[n] 청크의 실제 발언자 반환 (1-based 인덱스)."""
    if 1 <= n <= len(docs):
        return _doc_speaker_label(docs[n - 1])
    return ""


def _query_speaker_matches_chunk(chunk_speaker: str, kw: list[str]) -> bool:
    """청크 발언자가 질문 주체 키워드(3글자 이상)를 모두 포함하는지 확인.
    3글자 이상 키워드가 없으면(직함만) 필터 안 함.
    """
    if not kw or not chunk_speaker:
        return True
    specific = [k for k in kw if len(k) >= 3]
    if not specific:
        return True
    return all(k in chunk_speaker for k in specific)


def _chunk_matches_subject(chunk_speaker: str, subj_kw: list[str]) -> bool:
    """청크 발언자가 비교 주체 키워드 중 3글자 이상과 모두 일치하는지 확인."""
    if not subj_kw or not chunk_speaker:
        return False
    specific = [k for k in subj_kw if len(k) >= 3]
    if not specific:
        return any(k in chunk_speaker for k in subj_kw)
    return all(k in chunk_speaker for k in specific)


def _find_matching_subject(
    chunk_speaker: str, comparison_subjects: list[list[str]]
) -> int:
    """청크 발언자가 비교 주체 중 어느 쪽인지 인덱스 반환. 해당 없으면 -1."""
    for i, subj in enumerate(comparison_subjects):
        if _chunk_matches_subject(chunk_speaker, subj):
            return i
    return -1


def _validate_speaker_bullets(
    ans: str,
    docs: list[dict],
    query_speaker_kw: list[str],
    comparison_subjects: list[list[str]] | None = None,
) -> tuple[str, bool]:
    """
    세부 근거 불릿 2중 검증:
    - 단독 쿼리 Bug B: 청크 발언자가 질문 주체와 무관 → ## 확인된 범위로 이동
    - 단독 쿼리 Bug A: 불릿 명시 발언자 ≠ 실제 청크 발언자 → 실제 발언자로 교정
    - 비교 쿼리: 청크 발언자가 두 주체 중 어느 쪽도 아닌 제3자 → ## 확인된 범위로 이동
    - 비교 쿼리: 명시 발언자와 청크 발언자가 다른 주체이거나 제3자 → ## 확인된 범위로 이동
    반환: (수정된 답변, 변경 여부)
    """
    if not docs:
        return ans, False

    comp = comparison_subjects or []
    lines = ans.splitlines()
    in_detail = False
    out: list[str] = []
    moved: list[str] = []
    changed = False

    for line in lines:
        s = line.strip()

        if re.match(r"#{1,4}\s*세부\s*근거", s):
            in_detail = True
            out.append(line)
            continue
        if in_detail and s.startswith("## "):
            in_detail = False

        if not in_detail or not s.startswith("-"):
            out.append(line)
            continue

        cites = [int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", s)]
        if not cites:
            out.append(line)
            continue

        n = cites[0]
        chunk_speaker = _get_chunk_speaker(docs, n)
        import sys as _sys
        print(f"[DBG] bullet n={n} chunk_speaker='{chunk_speaker}' comp={comp} s='{s[:60]}'", file=_sys.stderr)

        if comp:
            # 비교 쿼리: 청크 발언자가 두 주체 중 하나인지 확인
            subj_idx = _find_matching_subject(chunk_speaker, comp)
            if chunk_speaker and subj_idx < 0:
                # 볼드 레이블(명시 발언자)이 비교 주체인지 확인
                bm_pre = _BULLET_BOLD_RE.match(s)
                stated_label = bm_pre.group(2).strip() if bm_pre else ""
                label_subj_idx = _find_matching_subject(stated_label, comp) if stated_label else -1

                if label_subj_idx >= 0:
                    # LLM이 비교 주체 이름으로 불릿 작성했지만 실제 청크는 제3자 발언
                    # → 발언자 허위 귀속: 확인된 범위로 이동 (유지하면 오정보 노출)
                    moved.append(
                        f"- {s.lstrip('- ').strip()} "
                        f"*(발언자 불일치: {stated_label} 발언 아님 — 실제 출처 {chunk_speaker})*"
                    )
                    changed = True
                    print(
                        f"[GroundingCheck] 비교쿼리 발언자 불일치 → 확인된 범위 이동: "
                        f"'{stated_label}' ← {chunk_speaker}"
                    )
                    continue

                # 볼드 레이블도 비교 주체가 아닌 완전한 제3자 → 확인된 범위로 이동
                moved.append(
                    f"- {s.lstrip('- ').strip()} "
                    f"*(직접 발언 아님: {chunk_speaker} 발언 기반)*"
                )
                changed = True
                print(f"[GroundingCheck] 비교쿼리 제3자 발언 이동: '{chunk_speaker}'")
                continue

            # 비교 쿼리 Bug A: 명시 발언자가 다른 주체이거나 제3자인지 확인
            bm = _BULLET_BOLD_RE.match(s)
            if bm and chunk_speaker and subj_idx >= 0:
                stated = bm.group(2).strip()
                stated_idx = _find_matching_subject(stated, comp)
                if stated_idx >= 0 and stated_idx != subj_idx:
                    # 다른 주체의 발언을 이 주체 것으로 표기
                    moved.append(
                        f"- {s.lstrip('- ').strip()} "
                        f"*(발언자 불일치: {chunk_speaker} 발언)*"
                    )
                    changed = True
                    print(
                        f"[GroundingCheck] 비교쿼리 발언자 혼동: "
                        f"명시='{stated}' 실제='{chunk_speaker}'"
                    )
                    continue
                if stated_idx < 0 and not _speaker_name_matches(stated, chunk_speaker):
                    # 제3자로 명시됐지만 실제 청크는 비교 주체 → 이름 교정
                    indent = " " * (len(line) - len(line.lstrip()))
                    corrected = f"{indent}{bm.group(1)}{chunk_speaker}{bm.group(3)}{bm.group(4)}"
                    out.append(corrected)
                    changed = True
                    print(f"[GroundingCheck] 비교쿼리 발언자 교정: '{stated}' → '{chunk_speaker}'")
                    continue
        else:
            # 단독 쿼리 Bug B: 질문 주체 키워드와 청크 발언자 불일치 → 확인된 범위로 이동
            if (
                query_speaker_kw
                and chunk_speaker
                and not _query_speaker_matches_chunk(chunk_speaker, query_speaker_kw)
            ):
                moved.append(f"- {s.lstrip('- ').strip()} *(질문 주체 외 발언자)*")
                changed = True
                print(f"[GroundingCheck] 타인 발언 이동: '{chunk_speaker}' kw={query_speaker_kw}")
                continue

            # 단독 쿼리 Bug A: 불릿 명시 발언자 ≠ 청크 실제 발언자 → 실제 발언자로 교정
            bm = _BULLET_BOLD_RE.match(s)
            if bm and chunk_speaker:
                stated = bm.group(2).strip()
                if not _speaker_name_matches(stated, chunk_speaker):
                    indent = " " * (len(line) - len(line.lstrip()))
                    corrected = f"{indent}{bm.group(1)}{chunk_speaker}{bm.group(3)}{bm.group(4)}"
                    out.append(corrected)
                    changed = True
                    print(f"[GroundingCheck] 발언자 교정: '{stated}' → '{chunk_speaker}'")
                    continue

        out.append(line)

    if moved:
        result = "\n".join(out)
        note = (
            "\n\n*(아래 항목은 질문 주체 외 발언자 내용입니다.)*\n"
            + "\n".join(moved)
        )
        limit_header = "## 확인된 범위"
        if limit_header in result:
            result = result.replace(limit_header, limit_header + note, 1)
        else:
            result = result.rstrip() + f"\n\n{limit_header}{note}"
        return result, True

    return "\n".join(out), changed


def _check_per_subject_grounding(
    ans: str, docs: list[dict], comparison_subjects: list[list[str]]
) -> tuple[str, bool]:
    """
    비교 질문 전용 후처리 (4단계):
    1) 핵심 결론의 제3자 출처 [n] 제거 — 비교 주체 발언이 아닌 인용 번호 삭제
    2) 한계 섹션 기존 LLM 생성 '비교 근거 부족' 항목 정리
    3) 한쪽 인물 근거 없으면 핵심 결론 앞에 편향 경고 삽입
    4) 근거 없는 주체에 한계 '비교 근거 부족' 항목 추가
    반환: (수정된 답변, 변경 여부)
    """
    if not comparison_subjects or not docs:
        return ans, False

    # ── 세부 근거에서 주체별 증거 탐지 ─────────────────────────────
    subject_has_evidence = [False] * len(comparison_subjects)
    in_detail = False
    for line in ans.splitlines():
        s = line.strip()
        if re.match(r"#{1,4}\s*세부\s*근거", s):
            in_detail = True
            continue
        if in_detail and s.startswith("## "):
            break
        if not in_detail or not s.startswith("-"):
            continue
        cites = [int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", s)]
        if not cites:
            continue
        chunk_speaker = _get_chunk_speaker(docs, cites[0])
        idx = _find_matching_subject(chunk_speaker, comparison_subjects)
        if idx >= 0:
            subject_has_evidence[idx] = True
            continue
        bm_e = _BULLET_BOLD_RE.match(s)
        label = bm_e.group(2).strip() if bm_e else ""
        if label:
            for i, subj in enumerate(comparison_subjects):
                if _chunk_matches_subject(label, subj):
                    subject_has_evidence[i] = True

    missing = [i for i, has in enumerate(subject_has_evidence) if not has]
    found = [i for i, has in enumerate(subject_has_evidence) if has]
    changed = False

    # ── 1) 핵심 결론 내 제3자 출처 [n] 제거 ───────────────────────
    # 비교 주체 발언이 아닌 청크의 인용 번호 → 제거
    # → _move_uncited_to_limits 에서 해당 문장에 *(출처 미확인)* 표시됨
    _strip_flag = [False]

    def _strip_if_thirdparty(m: re.Match) -> str:
        n = int(m.group(1))
        if n < 1 or n > len(docs):
            return m.group(0)
        sp = _get_chunk_speaker(docs, n)
        if not sp:
            return m.group(0)
        for subj in comparison_subjects:
            if _chunk_matches_subject(sp, subj):
                return m.group(0)
        _strip_flag[0] = True
        return ""

    lines = ans.splitlines()
    in_conclusion = False
    new_lines: list[str] = []
    for line in lines:
        s = line.strip()
        if _MAIN_HEADER_RE.match(s):
            in_conclusion = True
            new_lines.append(line)
            continue
        if in_conclusion and s.startswith("## "):
            in_conclusion = False
        if in_conclusion:
            new_lines.append(re.sub(r"\[(\d+)\]", _strip_if_thirdparty, line))
        else:
            new_lines.append(line)
    if _strip_flag[0]:
        ans = "\n".join(new_lines)
        changed = True
        print("[GroundingCheck] 핵심 결론 제3자 인용 제거")

    # ── 2) 한계 섹션 기존 '비교 근거 부족' 항목 정리 ─────────────
    lines = ans.splitlines()
    in_limits = False
    new_lines = []
    for line in lines:
        s = line.strip()
        if re.match(r"#{1,4}\s*(?:한계|확인된\s*범위)", s):
            in_limits = True
            new_lines.append(line)
            continue
        if in_limits and s.startswith("## "):
            in_limits = False
        if in_limits:
            if s == "*(비교 근거 부족)*":
                changed = True
                continue
            if s.startswith("-"):
                remove_it = False
                for subj in comparison_subjects:
                    if any(k in s for k in subj if len(k) >= 3) and _COMP_MISSING_RE.search(s):
                        remove_it = True
                        break
                if remove_it:
                    changed = True
                    continue
        new_lines.append(line)
    ans = "\n".join(new_lines)

    # ── 3) 한쪽 근거 없음 → 핵심 결론 앞에 편향 경고 삽입 ─────────
    if missing:
        found_names = [" ".join(comparison_subjects[i]) for i in found]
        missing_names = [" ".join(comparison_subjects[i]) for i in missing]
        if found_names:
            disclaimer = (
                f"*(⚠ {', '.join(missing_names)}의 직접 발언이 회의록에서 확인되지 않아 "
                f"정확한 비교가 어렵습니다. {', '.join(found_names)}의 입장만 일부 확인되었습니다.)*"
            )
        else:
            disclaimer = "*(⚠ 비교 대상 두 인물의 직접 발언이 모두 회의록에서 확인되지 않았습니다.)*"

        lines = ans.splitlines()
        new_lines = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if not inserted and _MAIN_HEADER_RE.match(line.strip()):
                new_lines.append("")
                new_lines.append(disclaimer)
                inserted = True
        if inserted:
            ans = "\n".join(new_lines)
            changed = True

    # ── 4) 근거 없는 주체에 한계 항목 추가 ────────────────────────
    if missing:
        notes = []
        for i in missing:
            subj_name = " ".join(comparison_subjects[i])
            notes.append(
                f"- **{subj_name}**: 직접 발언 근거를 회의록에서 찾을 수 없어 비교 근거 부족"
            )
        note_text = "\n*(비교 근거 부족)*\n" + "\n".join(notes)
        limit_header = "## 확인된 범위"
        if limit_header in ans:
            ans = ans.replace(limit_header, limit_header + note_text, 1)
        else:
            ans = ans.rstrip() + f"\n\n{limit_header}{note_text}"
        changed = True

    return ans, changed


def _remove_unlabeled_detail_section(ans: str) -> tuple[str, bool]:
    """세부 근거 불릿에 **발언자**: 볼드 레이블이 하나도 없으면 섹션 전체 제거.
    발언자가 불분명한 세부 근거는 오히려 혼란을 줄 수 있어 노출하지 않는다.
    """
    lines = ans.splitlines()
    detail_start = -1
    detail_end = -1
    has_bold_bullet = False

    for i, line in enumerate(lines):
        s = line.strip()
        if re.match(r"#{1,4}\s*세부\s*근거", s):
            detail_start = i
            continue
        if detail_start >= 0 and detail_end < 0:
            if s.startswith("## "):
                detail_end = i
                break
            if _BULLET_BOLD_RE.match(s):
                has_bold_bullet = True

    if detail_start < 0 or has_bold_bullet:
        return ans, False

    end = detail_end if detail_end >= 0 else len(lines)
    # 섹션 앞뒤 빈 줄도 함께 제거
    start = detail_start
    while start > 0 and lines[start - 1].strip() == "":
        start -= 1
    new_lines = lines[:start] + lines[end:]
    return "\n".join(new_lines), True


# 한계 섹션에서 세부 근거와 모순되는 "직접 발언 확인 불가" 패턴
_LIMITS_CONTRADICTION_RE = re.compile(
    r"[^\n]*(?:직접\s*발언|직접\s*인용)[^\n]*(?:확인되지|확인할\s*수\s*없|없습니다)[^\n]*"
)


def _remove_contradictory_limits(ans: str) -> tuple[str, bool]:
    """
    세부 근거에 [n] 인용이 있는데 한계에 '직접 발언이 확인 안 됨' 류 모순 문구 → 해당 줄 제거.
    """
    # 세부 근거에 실제 [n] 인용이 있는지 먼저 확인
    in_detail = False
    detail_has_cite = False
    for line in ans.splitlines():
        s = line.strip()
        if re.match(r"#{1,4}\s*세부\s*근거", s):
            in_detail = True
            continue
        if in_detail:
            if s.startswith("## "):
                break
            if re.search(r"\[\d+\]", s):
                detail_has_cite = True
                break

    if not detail_has_cite:
        return ans, False

    # 한계 섹션에서 모순 문구 제거
    lines = ans.splitlines()
    in_limits = False
    out: list[str] = []
    changed = False

    for line in lines:
        s = line.strip()
        if re.match(r"#{1,4}\s*(?:한계|확인된\s*범위)", s):
            in_limits = True
            out.append(line)
            continue
        if in_limits and s.startswith("## "):
            in_limits = False
        if in_limits and _LIMITS_CONTRADICTION_RE.search(s):
            changed = True
            print(f"[GroundingCheck] 확인된 범위 모순 문구 제거: '{s[:60]}'")
            continue
        out.append(line)

    return "\n".join(out), changed


def _is_meaningful(line: str) -> bool:
    s = line.strip()
    return bool(s) and not _SKIP.match(s) and len(s) > 10


def _pre_normalize(ans: str) -> str:
    """grounding 점수 계산 전: 헤더와 본문이 같은 줄에 붙어있으면 분리.
    공백 1개 이상으로 붙은 경우도 처리 (LLM이 ## 헤더 뒤 바로 본문 쓰는 경우).
    """
    # 헤더 키워드(메인 결과|핵심 결론|세부 근거|확인된 범위|참고 자료) 뒤 공백 1개 이상으로 붙은 본문 분리
    t = re.sub(
        r"(#{1,4}\s+(?:메인\s*결과|핵심\s*결론|세부\s*근거|확인된\s*범위|참고\s*자료|한계)[^\n]*?)\s+([가-힣\-\*])",
        r"\1\n\2",
        ans,
    )
    # 그 외 헤더: 공백 2개 이상이면 분리
    t = re.sub(r"(#{1,4}\s[^\n]+?)\s{2,}([^#\n])", r"\1\n\2", t)
    return t


def _grounding_score(ans: str) -> float:
    """의미 있는 줄 중 [n] 인용이 있는 줄 비율 (0.0 ~ 1.0).
    ## 헤더 줄이라도 [n]이 포함되어 있으면 의미 있는 줄로 처리.
    """
    lines = [l.strip() for l in _pre_normalize(ans).splitlines()]
    meaningful: list[str] = []
    for l in lines:
        if not l:
            continue
        has_cite = bool(re.search(r"\[\d+\]", l))
        if _is_meaningful(l) or has_cite:
            meaningful.append(l)
    if not meaningful:
        return 0.0
    cited = sum(1 for l in meaningful if re.search(r"\[\d+\]", l))
    return cited / len(meaningful)


def _is_weak_retrieval(docs: list[dict]) -> bool:
    """검색 결과가 답변 생성에 부족한지 판단."""
    if len(docs) < MIN_DOCS_FOR_ANSWER:
        return True
    scores: list[float] = []
    for d in docs:
        s = d.get("rerank_score") or d.get("similarity") or d.get("score") or 0.0
        try:
            scores.append(float(s))
        except (TypeError, ValueError):
            pass
    return bool(scores) and max(scores) < WEAK_SCORE_THRESHOLD


def _fix_out_of_range(ans: str, num_docs: int) -> tuple[str, list[int]]:
    """[n]이 [1..num_docs] 밖이면 [?]로 교체. (수정 답변, 위반 번호 목록) 반환."""
    if num_docs <= 0:
        return ans, []
    bad: list[int] = []

    def _replace(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= num_docs:
            return m.group(0)
        bad.append(n)
        return "[?]"

    return re.sub(r"\[(\d+)\]", _replace, ans), bad


def _move_uncited_to_limits(ans: str) -> tuple[str, bool]:
    """
    ## 세부 근거 불릿 중 [n] 없는 줄 → ## 확인된 범위로 이동.
    ## 핵심 결론의 미인용 주요 문장 → 인라인 *(출처 미확인)* 표시.
    반환: (수정된 답변, 이동이 실제로 발생했는지)
    """
    lines = ans.splitlines()
    section = ""        # 현재 섹션
    moved: list[str] = []
    out: list[str] = []

    for line in lines:
        stripped = line.strip()

        # 섹션 헤더 감지
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            out.append(line)
            continue

        # 의미 없는 줄 → 그대로
        if not _is_meaningful(line):
            out.append(line)
            continue

        has_cite = bool(re.search(r"\[\d+\]", stripped))

        if section.startswith("세부 근거") and stripped.startswith("-"):
            # 불릿 줄
            if has_cite:
                out.append(line)
            else:
                # 확인된 범위로 이동
                moved.append(f"- {stripped.lstrip('- ').strip()} *(출처 미확인)*")
        elif section.startswith(("핵심 결론", "메인 결과")) and not has_cite:
            # 메인 결과/핵심 결론의 미인용 문장 → 인라인 표시
            out.append(line.rstrip() + " *(출처 미확인)*")
        else:
            out.append(line)

    if not moved:
        return "\n".join(out), False

    result = "\n".join(out)

    # ## 확인된 범위 섹션에 이동된 항목 추가
    limit_header = "## 확인된 범위"
    limit_note = (
        "\n\n*(아래 내용은 회의록에서 직접 인용 번호를 확인하지 못한 항목입니다.)*\n"
        + "\n".join(moved)
    )
    if limit_header in result:
        # 한계 섹션 직후에 삽입
        result = result.replace(
            limit_header,
            limit_header + limit_note,
            1,
        )
    else:
        result = result.rstrip() + f"\n\n{limit_header}{limit_note}"

    return result, True


def _check_citation_support(ans: str, docs: list[dict]) -> list[str]:
    """
    [n] 인용 문장에서 해당 청크 텍스트와 한국어 키워드 오버랩을 체크.
    오버랩이 전혀 없는 인용 → 의심 목록 반환 (로그·경고용).
    """
    warnings: list[str] = []
    if not docs:
        return warnings

    for line in ans.splitlines():
        s = line.strip()
        if not _is_meaningful(s):
            continue
        for m in re.finditer(r"\[(\d+)\]", s):
            n = int(m.group(1))
            if n < 1 or n > len(docs):
                continue
            chunk = (docs[n - 1].get("chunk_text") or "").strip()
            # 2글자 이상 한국어 어절 추출
            claim_words = set(re.findall(r"[가-힣]{2,}", s))
            chunk_words = set(re.findall(r"[가-힣]{2,}", chunk))
            overlap = claim_words & chunk_words
            if claim_words and not overlap:
                warnings.append(
                    f"[n={n}] 인용 청크와 키워드 오버랩 없음 → '{s[:60]}...'"
                )
    return warnings


# ── 노드 진입점 ───────────────────────────────────────────────────

def run(state: QAState) -> QAState:
    ans  = state.get("draft_answer", "") or ""
    docs = state.get("reranked") or state.get("retrieved") or []

    # ── 기준 5: 검색 결과가 약하면 거부 ──────────────────────────
    is_weak = _is_weak_retrieval(docs)
    if (
        docs
        and is_weak
        and ans.strip()
        and not state.get("generation_skipped")
        and not state.get("llm_error_kind")
    ):
        state["draft_answer"] = _REFUSAL_WEAK
        state["grounded"]        = False
        state["grounding_score"] = 0.0
        state["grounding_level"] = "NONE"
        print("[GroundingCheck] REFUSED: weak retrieval")
        return state

    # ── 기준 2: [n] 범위 검증 ────────────────────────────────────
    if ans.strip() and docs:
        ans, bad_nums = _fix_out_of_range(ans, len(docs))
        if bad_nums:
            print(f"[GroundingCheck] out-of-range citations fixed: {bad_nums}")
        state["draft_answer"] = ans

    # ── 핵심 결론 '확인 불가' → 세부 근거 제거 ───────────────────
    if ans.strip():
        ans, stripped = _strip_detail_if_conclusion_refusal(ans)
        if stripped:
            state["draft_answer"] = ans
            print("[GroundingCheck] 세부 근거 제거: 핵심 결론이 확인 불가 패턴")

    # ── 발언자 검증: 타인 발언 이동 + 이름 교정 ──────────────────
    spk_changed = False
    if ans.strip() and docs:
        _meta = state.get("meta") or {}
        _qsk = list(_meta.get("query_speaker_kw") or [])
        _comp = list(_meta.get("query_comparison_subjects") or [])
        ans, spk_changed = _validate_speaker_bullets(ans, docs, _qsk, _comp or None)
        if spk_changed:
            state["draft_answer"] = ans

    # ── 비교 쿼리: 인물별 근거 존재 여부 판정 ────────────────────
    if ans.strip() and docs:
        _comp = list((state.get("meta") or {}).get("query_comparison_subjects") or [])
        if _comp:
            ans, grnd_changed = _check_per_subject_grounding(ans, docs, _comp)
            if grnd_changed:
                state["draft_answer"] = ans

    # ── 한계 모순 문구 제거 (세부 근거에 인용 있는데 '확인 안 됨') ─
    # 반드시 _remove_unlabeled_detail_section 전에 실행 — 세부 근거가 먼저 제거되면 인용 탐지 불가
    if ans.strip():
        ans, lim_changed = _remove_contradictory_limits(ans)
        if lim_changed:
            state["draft_answer"] = ans

    # ── 볼드 레이블 없는 세부 근거 섹션 제거 ────────────────────────
    if ans.strip():
        ans, unlabeled = _remove_unlabeled_detail_section(ans)
        if unlabeled:
            state["draft_answer"] = ans
            print("[GroundingCheck] 세부 근거 제거: 볼드 발언자 레이블 없음")

    # ── grounding 점수·레벨 계산 ──────────────────────────────────
    score = _grounding_score(ans) if ans.strip() else 0.0

    if score > CITE_FULL_THRESHOLD:
        level = "FULL"
    elif score > 0:
        level = "PARTIAL"
    else:
        level = "NONE"

    state["grounded"]        = score > 0
    state["grounding_score"] = round(score, 3)
    state["grounding_level"] = level

    # ── 경고·수정이 필요한 조건 ───────────────────────────────────
    should_process = (
        docs
        and ans.strip()
        and not state.get("generation_skipped")
        and not state.get("llm_error_kind")
    )

    if should_process:
        # ── 기준 4: 미인용 문장 → ## 확인된 범위로 이동 ─────────────────
        if level in ("PARTIAL", "NONE"):
            ans, moved = _move_uncited_to_limits(ans)
            state["draft_answer"] = ans
            if moved:
                print("[GroundingCheck] uncited sentences moved to 확인된 범위")

        # ── 기준 1/전체: 최종 경고 ────────────────────────────────
        _is_comp = bool((state.get("meta") or {}).get("query_comparison_subjects"))
        if level == "NONE":
            state["draft_answer"] = ans.rstrip() + _WARN_NONE
        elif level == "PARTIAL":
            # 비교 쿼리에서 발언자 불일치가 발견된 경우 전용 경고 사용
            if _is_comp and spk_changed:
                state["draft_answer"] = ans.rstrip() + _WARN_SPEAKER_MISMATCH
            else:
                state["draft_answer"] = ans.rstrip() + _WARN_PARTIAL

        # ── 기준 3: 인용-청크 지지 체크 (로그용) ──────────────────
        support_warns = _check_citation_support(ans, docs)
        if support_warns:
            print(f"[GroundingCheck] citation support warnings ({len(support_warns)}건):")
            for w in support_warns[:5]:
                print(f"  {w}")

    print(
        f"[GroundingCheck] level={level} score={score:.2f} "
        f"docs={len(docs)} weak={is_weak} "
        f"warned={'yes' if should_process and level != 'FULL' else 'no'}"
    )
    return state
