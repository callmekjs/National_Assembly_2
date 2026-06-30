from __future__ import annotations

import json
import re
from pathlib import Path

from service.speaker_aliases import has_hanja, normalize_speaker_name

ROOT = Path(__file__).resolve().parents[3]
NORM_DIR = ROOT / "data" / "v2" / "transform" / "normalized"
OUT_DIR = ROOT / "data" / "v2" / "transform" / "turns"

_ROLE_SUFFIXES = (
    "수석전문위원",
    "전문위원",
    "소위원장",
    "공직후보자",
    "후보자",
    "위원장",
    "사무처장",
    "본부장",
    "센터장",
    "부장관",
    "비서관",
    "조정관",
    "위원",
    "의원",
    "장관",
    "차관",
    "대사",
    "국장",
    "과장",
    "처장",
    "원장",
    "청장",
    "실장",
    "차장",
    "후보",
)
_ROLE_SUFFIX_RE = "|".join(re.escape(s) for s in _ROLE_SUFFIXES)
_ROLE_RE = rf"[가-힣A-Za-z0-9·ㆍ-]{{0,35}}(?:{_ROLE_SUFFIX_RE})"
_NAME_RE = r"[가-힣\u3400-\u9fff\uf900-\ufaff]{2,4}"

_SPEAKER_PATTERNS = (
    # ◯외교부장관 조태열 ... / ◯위원장 김석기 ...
    re.compile(rf"^[○◯]\s*(?P<role>{_ROLE_RE})\s+(?P<speaker>{_NAME_RE})(?=\s|$)(?P<body>.*)", re.DOTALL),
    # ◯외교부장관조태열 ... 처럼 OCR이 공백을 잃은 경우
    re.compile(rf"^[○◯]\s*(?P<role>{_ROLE_RE})(?P<speaker>{_NAME_RE})(?=\s|$)(?P<body>.*)", re.DOTALL),
    # ◯조태열 장관 ... / ◯김석기 위원장 ...
    re.compile(rf"^[○◯]\s*(?P<speaker>{_NAME_RE})\s+(?P<role>{_ROLE_RE})(?=\s|$)(?P<body>.*)", re.DOTALL),
    # ◯조태열장관 ... 처럼 OCR이 공백을 잃은 경우
    re.compile(rf"^[○◯]\s*(?P<speaker>{_NAME_RE})(?P<role>{_ROLE_RE})(?=\s|$)(?P<body>.*)", re.DOTALL),
    # ◯정부측 ... / ◯의안 ... 등 인물명이 아닌 진행 표지도 일단 보존
    re.compile(r"^[○◯]\s*(?P<speaker>[가-힣A-Za-z0-9·ㆍ\-\u3400-\u9fff\uf900-\ufaff]{2,20})(?=\s|$)(?P<body>.*)", re.DOTALL),
)


def _parse_speaker_marker(segment: str) -> tuple[str, str, str] | None:
    for pattern in _SPEAKER_PATTERNS:
        m = pattern.match(segment)
        if not m:
            continue
        speaker = (m.groupdict().get("speaker") or "").strip()
        role = (m.groupdict().get("role") or "").strip()
        body = (m.groupdict().get("body") or "").strip()
        return normalize_speaker_name(speaker), role, body
    return None


def extract_turns(
    source_id: str,
    page_no: int,
    clean_text: str,
    default_speaker: str = "",
    default_role: str = "",
) -> list[dict]:
    turns: list[dict] = []
    parts = re.split(r"(?=[○◯])", clean_text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        parsed = _parse_speaker_marker(part)
        if not parsed:
            if len(part) > 50:
                turns.append({
                    "source_id": source_id,
                    "page_no": page_no,
                    "turn_index": len(turns),
                    "speaker": default_speaker,
                    "speaker_role": default_role,
                    "section_type": "body",
                    "clean_text": part,
                })
            continue
        speaker, role, body = parsed
        if not body:
            continue
        turn = {
            "source_id": source_id,
            "page_no": page_no,
            "turn_index": len(turns),
            "speaker": speaker,
            "speaker_role": role,
            "section_type": "body",
            "clean_text": body,
        }
        raw_marker = part.split(body, 1)[0] if body else part
        raw_hanja = re.search(r"[\u3400-\u9fff\uf900-\ufaff]{2,5}", raw_marker)
        if raw_hanja and has_hanja(raw_hanja.group(0)):
            turn["speaker_original"] = raw_hanja.group(0)
        turns.append(turn)
    return turns


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_turns = 0

    for norm_path in sorted(NORM_DIR.glob("*/normalized.jsonl")):
        sid = norm_path.parent.name
        src_out = OUT_DIR / sid
        src_out.mkdir(parents=True, exist_ok=True)
        out_path = src_out / "turns.jsonl"
        turn_idx = 0
        last_speaker = ""
        last_role = ""

        with norm_path.open("r", encoding="utf-8") as src, \
             out_path.open("w", encoding="utf-8") as out:
            for line in src:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("section_type") != "body":
                    continue
                for t in extract_turns(
                    sid,
                    row["page_no"],
                    row.get("clean_text", ""),
                    default_speaker=last_speaker,
                    default_role=last_role,
                ):
                    t["turn_index"] = turn_idx
                    t["metadata"] = row.get("metadata", {})
                    if t.get("speaker"):
                        last_speaker = t.get("speaker", "")
                        last_role = t.get("speaker_role", "")
                    turn_idx += 1
                    out.write(json.dumps(t, ensure_ascii=False) + "\n")
                    total_turns += 1

    print(f"[parser_v2] turns={total_turns} → {OUT_DIR}/{{source_id}}/turns.jsonl")


if __name__ == "__main__":
    main()
