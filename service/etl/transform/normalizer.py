from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IN_PATH = ROOT / "data" / "transform" / "parser" / "parsed.jsonl"
OUT_DIR = ROOT / "data" / "transform" / "normalized"


def _normalize_text(text: str) -> str:
    # PDF 추출 후 자주 섞이는 제어문자 제거
    text = text.replace("\x00", " ").replace("\ufeff", " ")
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", text)

    # 줄 단위 정규화: 비정상 공백/탭 정리
    lines: list[str] = []
    for line in text.splitlines():
        line = line.replace("\t", " ")
        line = re.sub(r"[ ]{2,}", " ", line).strip()
        if line:
            lines.append(line)

    text = "\n".join(lines)

    # 과도한 반복 기호 축소 (예: 깨진 출력에서 "��" 연속)
    text = re.sub(r"(�){2,}", "�", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _first_match(pattern: str, text: str) -> str:
    m = re.search(pattern, text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def _normalize_metadata(metadata: dict, text: str) -> dict:
    md = dict(metadata or {})

    # speaker fallback: 회의록 본문에서 "◯위원장/◯소위원장 ..." 패턴 우선 추출
    speaker = str(md.get("speaker", "")).strip()
    if not speaker:
        speaker = _first_match(r"◯\s*([^\s\n()]+)", text)
        if speaker:
            md["speaker"] = speaker

    # committee fallback: 헤더의 "...위원회회의록"에서 추출
    committee = str(md.get("committee", "")).strip()
    if not committee:
        committee = _first_match(r"([가-힣A-Za-z0-9·]+위원회)회의록", text)
        if committee:
            md["committee"] = committee

    # meeting_date fallback: "YYYY년M월D일"을 표준 형식으로 정규화
    meeting_date = str(md.get("meeting_date", "")).strip()
    if not meeting_date:
        d = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
        if d:
            yyyy, mm, dd = d.group(1), int(d.group(2)), int(d.group(3))
            md["meeting_date"] = f"{yyyy}-{mm:02d}-{dd:02d}"

    return md


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "normalized.jsonl"
    count = 0
    if not IN_PATH.exists():
        out_path.write_text("", encoding="utf-8")
        print(f"[normalizer] no input: {IN_PATH}")
        return

    with IN_PATH.open("r", encoding="utf-8") as src, out_path.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.strip():
                continue
            row = json.loads(line)
            row["text"] = _normalize_text(str(row.get("text", "")))
            if not row["text"]:
                continue
            row["metadata"] = _normalize_metadata(row.get("metadata", {}), row["text"])
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    print(f"[normalizer] normalized={count} -> {out_path}")


if __name__ == "__main__":
    main()
