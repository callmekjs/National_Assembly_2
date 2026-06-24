from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NORM_DIR = ROOT / "data" / "v2" / "transform" / "normalized"
OUT_DIR = ROOT / "data" / "v2" / "transform" / "turns"

_ROLES = (
    "위원장|소위원장|수석전문위원|전문위원|위원|장관|차관|의원|대사"
    "|국장|과장|처장|원장|청장|부장관|실장|본부장|비서관"
)

_SPEAKER_RE = re.compile(
    r"◯\s*"
    r"(?:(" + _ROLES + r")\s+([가-힣]+)"
    r"|([가-힣]+)\s+(" + _ROLES + r")"
    r"|([가-힣]+))"
)


def _parse_speaker(match: re.Match) -> tuple[str, str]:
    g = match.groups()
    if g[0]:
        return g[1].strip(), g[0].strip()
    if g[2]:
        return g[2].strip(), g[3].strip()
    return (g[4] or "").strip(), ""


def extract_turns(source_id: str, page_no: int, clean_text: str) -> list[dict]:
    turns: list[dict] = []
    parts = re.split(r"(?=◯)", clean_text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = _SPEAKER_RE.match(part)
        if not m:
            if len(part) > 50:
                turns.append({
                    "source_id": source_id,
                    "page_no": page_no,
                    "turn_index": len(turns),
                    "speaker": "",
                    "speaker_role": "",
                    "section_type": "body",
                    "clean_text": part,
                })
            continue
        speaker, role = _parse_speaker(m)
        body = part[m.end():].strip()
        if not body:
            continue
        turns.append({
            "source_id": source_id,
            "page_no": page_no,
            "turn_index": len(turns),
            "speaker": speaker,
            "speaker_role": role,
            "section_type": "body",
            "clean_text": body,
        })
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

        with norm_path.open("r", encoding="utf-8") as src, \
             out_path.open("w", encoding="utf-8") as out:
            for line in src:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("section_type") != "body":
                    continue
                for t in extract_turns(sid, row["page_no"], row.get("clean_text", "")):
                    t["turn_index"] = turn_idx
                    t["metadata"] = row.get("metadata", {})
                    turn_idx += 1
                    out.write(json.dumps(t, ensure_ascii=False) + "\n")
                    total_turns += 1

    print(f"[parser_v2] turns={total_turns} → {OUT_DIR}/{{source_id}}/turns.jsonl")


if __name__ == "__main__":
    main()
