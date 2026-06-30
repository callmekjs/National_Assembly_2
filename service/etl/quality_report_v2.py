from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FINAL_DIR = ROOT / "data" / "v2" / "transform" / "final"
QA_PATH = ROOT / "data" / "v2" / "transform" / "qa_pairs" / "qa_pairs_v2.jsonl"
REPORTS_DIR = ROOT / "data" / "v2" / "reports"
REPORT_PATH = REPORTS_DIR / "quality_report_v2.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HANJA_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
MARKER_RE = re.compile(
    r"[○◯]\s*(?P<speaker>[가-힣\u3400-\u9fff\uf900-\ufaff]{2,4})\s*"
    r"(?P<role>위원장|위원|의원|장관|차관|총장|원장|대표|의장|후보자|후보)"
)


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                yield line_no, json.loads(line), None
            except Exception as exc:
                yield line_no, {}, str(exc)


def _top(counter: Counter, n: int = 15) -> list[dict[str, Any]]:
    return [{"value": key, "count": count} for key, count in counter.most_common(n)]


def analyze_chunks(path: Path) -> dict[str, Any]:
    required = [
        "chunk_id",
        "source_id",
        "page_no",
        "turn_index",
        "section_type",
        "clean_text",
        "embed_text",
        "metadata",
    ]
    meta_required = [
        "committee",
        "meeting_date",
        "source_path",
        "token_count",
        "position_type",
        "utterance_type",
        "question_type_hints",
    ]

    rows = 0
    bad_json = 0
    seen: set[str] = set()
    duplicate_chunk_ids = 0
    missing_required = Counter()
    missing_meta = Counter()
    empty_meta = Counter()
    committee = Counter()
    years = Counter()
    section_type = Counter()
    position_type = Counter()
    utterance_type = Counter()
    agency = Counter()
    speaker_empty = 0
    role_empty = 0
    speaker_hanja = 0
    speaker_original = 0
    marker_mismatch = 0
    bad_date = 0
    source_path_missing = 0
    source_path_not_found = 0
    clean_empty = 0
    embed_empty = 0
    top_speaker = Counter()
    top_role = Counter()
    examples: dict[str, list] = {
        "marker_mismatch": [],
        "source_path_not_found": [],
        "empty_speaker": [],
    }

    for line_no, row, err in _iter_jsonl(path) or []:
        if err:
            bad_json += 1
            continue
        rows += 1
        chunk_id = str(row.get("chunk_id") or "")
        if chunk_id in seen:
            duplicate_chunk_ids += 1
        seen.add(chunk_id)

        for key in required:
            if key not in row:
                missing_required[key] += 1
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        for key in meta_required:
            if key not in meta:
                missing_meta[key] += 1
            elif meta.get(key) in ("", None, []):
                empty_meta[key] += 1

        committee[str(meta.get("committee") or "<empty>")] += 1
        date = str(meta.get("meeting_date") or "")
        if DATE_RE.match(date):
            years[date[:4]] += 1
        else:
            bad_date += 1
        section_type[str(row.get("section_type") or "<empty>")] += 1
        position_type[str(meta.get("position_type") or "<empty>")] += 1
        utterance_type[str(meta.get("utterance_type") or "<empty>")] += 1
        agency[str(meta.get("agency") or "<empty>")] += 1

        speaker = str(row.get("speaker") or meta.get("speaker") or "").strip()
        role = str(row.get("speaker_role") or meta.get("speaker_role") or "").strip()
        text = str(row.get("clean_text") or "")
        if not speaker:
            speaker_empty += 1
            if len(examples["empty_speaker"]) < 5:
                examples["empty_speaker"].append([line_no, chunk_id, text[:120]])
        if not role:
            role_empty += 1
        if HANJA_RE.search(speaker):
            speaker_hanja += 1
        if meta.get("speaker_original"):
            speaker_original += 1
        top_speaker[speaker or "<empty>"] += 1
        top_role[role or "<empty>"] += 1

        match = MARKER_RE.search(text[:600])
        if match and speaker:
            marker_speaker = match.group("speaker")
            if marker_speaker not in speaker and speaker not in marker_speaker:
                marker_mismatch += 1
                if len(examples["marker_mismatch"]) < 8:
                    examples["marker_mismatch"].append(
                        [line_no, chunk_id, speaker, marker_speaker, text[:140]]
                    )

        if not text.strip():
            clean_empty += 1
        if not str(row.get("embed_text") or "").strip():
            embed_empty += 1

        source_path = str(meta.get("source_path") or "")
        if not source_path:
            source_path_missing += 1
        elif not (ROOT / source_path.replace("\\", "/")).exists():
            source_path_not_found += 1
            if len(examples["source_path_not_found"]) < 5:
                examples["source_path_not_found"].append([line_no, chunk_id, source_path])

    return {
        "path": str(path.relative_to(ROOT)),
        "rows": rows,
        "bad_json": bad_json,
        "duplicate_chunk_ids": duplicate_chunk_ids,
        "bad_date": bad_date,
        "source_path_missing": source_path_missing,
        "source_path_not_found": source_path_not_found,
        "clean_empty": clean_empty,
        "embed_empty": embed_empty,
        "speaker_empty": speaker_empty,
        "role_empty": role_empty,
        "speaker_hanja": speaker_hanja,
        "speaker_original": speaker_original,
        "marker_mismatch": marker_mismatch,
        "missing_required": dict(missing_required),
        "missing_meta": dict(missing_meta),
        "empty_meta": dict(empty_meta),
        "committee": _top(committee),
        "years": _top(years),
        "section_type": _top(section_type),
        "position_type": _top(position_type),
        "utterance_type": _top(utterance_type),
        "agency": _top(agency),
        "top_speaker": _top(top_speaker),
        "top_role": _top(top_role),
        "examples": examples,
    }


def analyze_qa_pairs(path: Path) -> dict[str, Any]:
    rows = 0
    bad_json = 0
    seen: set[str] = set()
    duplicate_chunk_ids = 0
    committee = Counter()
    years = Counter()
    top_role = Counter()
    for _, row, err in _iter_jsonl(path) or []:
        if err:
            bad_json += 1
            continue
        rows += 1
        chunk_id = str(row.get("chunk_id") or "")
        if chunk_id in seen:
            duplicate_chunk_ids += 1
        seen.add(chunk_id)
        meta = row.get("metadata") or {}
        committee[str(meta.get("committee") or "<empty>")] += 1
        years[str(meta.get("meeting_date") or "")[:4] or "<empty>"] += 1
        top_role[str(row.get("speaker_role") or "<empty>")] += 1
    return {
        "path": str(path.relative_to(ROOT)),
        "rows": rows,
        "bad_json": bad_json,
        "duplicate_chunk_ids": duplicate_chunk_ids,
        "committee": _top(committee),
        "years": _top(years),
        "top_role": _top(top_role),
    }


def build_report() -> dict[str, Any]:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chunks_v2": analyze_chunks(FINAL_DIR / "chunks_v2.jsonl"),
        "qa_pairs_v2": analyze_qa_pairs(QA_PATH),
    }
    return report


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[quality_report_v2] → {REPORT_PATH}")
    print(
        "[quality_report_v2] chunks={rows} marker_mismatch={mm} speaker_original={orig}".format(
            rows=report["chunks_v2"]["rows"],
            mm=report["chunks_v2"]["marker_mismatch"],
            orig=report["chunks_v2"]["speaker_original"],
        )
    )


if __name__ == "__main__":
    main()
