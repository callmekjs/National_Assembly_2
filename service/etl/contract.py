"""
파이프라인 스키마 계약 (Schema Contract)
각 ETL 단계 출력 파일의 필수 필드와 형식을 검증한다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


# ── 검증 결과 ────────────────────────────────────────────────────

@dataclass
class FieldStats:
    name: str
    missing: int = 0
    invalid: int = 0
    total: int = 0

    @property
    def fill_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.total - self.missing) / self.total * 100, 1)


@dataclass
class ContractResult:
    stage: str
    total: int = 0
    errors: int = 0          # REQUIRED 필드 누락 → 해당 행 사용 불가
    warnings: int = 0        # WARN 필드 누락 → 품질 저하 가능
    field_stats: dict[str, FieldStats] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.errors == 0

    def report(self) -> str:
        lines = [
            f"[contract:{self.stage}] total={self.total} errors={self.errors} warnings={self.warnings}",
        ]
        for fs in self.field_stats.values():
            status = "✓" if fs.missing == 0 else ("✗" if fs.name.startswith("REQ:") else "△")
            lines.append(f"  {status} {fs.name.replace('REQ:','').replace('WARN:','')} fill={fs.fill_rate}%  missing={fs.missing}")
        for msg in self.messages[:5]:
            lines.append(f"  ! {msg}")
        if len(self.messages) > 5:
            lines.append(f"  ... 외 {len(self.messages)-5}건")
        return "\n".join(lines)


# ── 공통 검증 헬퍼 ────────────────────────────────────────────────

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _get(row: dict, *keys: str) -> str:
    """중첩 키 접근: _get(row, 'metadata', 'committee')"""
    val = row
    for k in keys:
        if not isinstance(val, dict):
            return ""
        val = val.get(k, "")
    return str(val or "").strip()


def _track(result: ContractResult, key: str, missing: bool) -> None:
    if key not in result.field_stats:
        result.field_stats[key] = FieldStats(name=key)
    fs = result.field_stats[key]
    fs.total += 1
    if missing:
        fs.missing += 1


# ── 단계별 검증 ───────────────────────────────────────────────────

def validate_extracted(path: Path) -> ContractResult:
    """Extract 단계: source_id·text 필수, meeting_date 형식 검증"""
    result = ContractResult(stage="extract")
    if not path.exists():
        result.messages.append(f"파일 없음: {path}")
        return result

    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            result.total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                result.errors += 1
                result.messages.append(f"line {i+1}: JSON 파싱 오류")
                continue

            # REQUIRED: source_id
            sid = _get(row, "source_id")
            _track(result, "REQ:source_id", not sid)
            if not sid:
                result.errors += 1
                result.messages.append(f"line {i+1}: source_id 없음")

            # REQUIRED: text (100자 이상)
            text = _get(row, "text")
            short = len(text) < 100
            _track(result, "REQ:text(≥100자)", not text or short)
            if not text:
                result.errors += 1
                result.messages.append(f"line {i+1}: text 없음")
            elif short:
                result.warnings += 1
                result.messages.append(f"line {i+1}: text 너무 짧음 ({len(text)}자)")

            # WARN: meeting_date 형식
            md = _get(row, "metadata", "meeting_date")
            invalid_date = bool(md) and not _DATE_RE.match(md)
            _track(result, "WARN:meeting_date", not md)
            if invalid_date:
                result.warnings += 1
                result.messages.append(f"line {i+1}: meeting_date 형식 오류 ({md!r})")

            # WARN: committee
            _track(result, "WARN:committee", not _get(row, "metadata", "committee"))

    return result


def validate_normalized(path: Path) -> ContractResult:
    """Normalize 단계: 메타데이터 채움 비율 검증"""
    result = ContractResult(stage="normalize")
    if not path.exists():
        result.messages.append(f"파일 없음: {path}")
        return result

    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            result.total += 1
            row = json.loads(line)

            _track(result, "WARN:committee",    not _get(row, "metadata", "committee"))
            _track(result, "WARN:meeting_date", not _get(row, "metadata", "meeting_date"))
            _track(result, "WARN:speaker",      not _get(row, "metadata", "speaker"))

            if not _get(row, "metadata", "committee"):
                result.warnings += 1
            if not _get(row, "metadata", "meeting_date"):
                result.warnings += 1

    return result


def validate_chunks(path: Path, min_len: int = 80) -> ContractResult:
    """Chunk 단계: chunk_id·content 필수, 짧은 청크 비율 검증"""
    result = ContractResult(stage="chunk")
    if not path.exists():
        result.messages.append(f"파일 없음: {path}")
        return result

    short_count = 0
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            result.total += 1
            row = json.loads(line)

            # REQUIRED: chunk_id
            cid = _get(row, "chunk_id")
            _track(result, "REQ:chunk_id", not cid)
            if not cid:
                result.errors += 1
                result.messages.append(f"line {i+1}: chunk_id 없음")

            # REQUIRED: content 또는 text
            content = _get(row, "content") or _get(row, "text")
            _track(result, "REQ:content", not content)
            if not content:
                result.errors += 1
                result.messages.append(f"line {i+1}: content/text 없음")
            elif len(content) < min_len:
                short_count += 1

            # WARN: committee, meeting_date
            _track(result, "WARN:committee",    not _get(row, "metadata", "committee"))
            _track(result, "WARN:meeting_date", not _get(row, "metadata", "meeting_date"))
            _track(result, "WARN:speaker",      not _get(row, "speaker"))

    if result.total > 0:
        short_pct = round(short_count / result.total * 100, 1)
        if short_pct > 10:
            result.warnings += 1
            result.messages.append(f"짧은 청크({min_len}자 미만) 비율 {short_pct}% ({short_count}개)")

    return result


# ── 전체 파이프라인 검증 ──────────────────────────────────────────

def validate_pipeline(root: Path) -> bool:
    """Extract → Normalize → Chunk 순서로 전체 검증. 오류 있으면 False 반환."""
    checks = [
        validate_extracted(root / "data/extract/extracted.jsonl"),
        validate_normalized(root / "data/transform/normalized/normalized.jsonl"),
        validate_chunks(root / "data/transform/final/chunks.jsonl"),
    ]
    all_ok = True
    for result in checks:
        print(result.report())
        if not result.ok:
            all_ok = False
    if all_ok:
        print("[contract] 전체 검증 통과 ✓")
    else:
        print("[contract] 오류 발견 — 파이프라인 재확인 필요 ✗")
    return all_ok


if __name__ == "__main__":
    validate_pipeline(Path(__file__).resolve().parents[2])
