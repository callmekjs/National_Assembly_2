from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXTRACT_DIR = ROOT / "data" / "v2" / "extract"
OUT_DIR = ROOT / "data" / "v2" / "transform" / "normalized"

_NOISE_LINE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^제\d+회[\-\s]?[가-힣]*제?\d*차?.*$"),
    re.compile(r"^국[\s·]*회[\s·]*사[\s·]*무[\s·]*처\s*$"),
    re.compile(r"^[가-힣]+위원회회의록\s*(제\d+호)?\s*$"),
    re.compile(r"^[-\s·]*\d+[-\s·]*$"),
    re.compile(r"^.*\.{4,}\s*\d+\s*$"),
    re.compile(r"^[-·\s.]{5,}$"),
]

_HEADER_RE = re.compile(r"[가-힣]+위원회\s*회의록\s*(제\d+호)?", re.MULTILINE)


def classify_section(raw_text: str) -> str:
    sample = raw_text[:600]
    if re.search(r"국\s*회\s*사\s*무\s*처", sample):
        return "cover"
    if "◯" in raw_text:
        return "body"
    if re.search(r"(의\s*사\s*일\s*정|상\s*정\s*된?\s*안\s*건|회\s*의\s*안\s*건)", sample):
        return "agenda"
    if re.search(r"(보\s*고\s*사\s*항|붙\s*임\s*\d)", sample):
        return "appendix"
    return "body"


def clean_text(raw: str) -> str:
    text = raw.replace("\x00", "").replace("﻿", "")
    text = re.sub(r"[​-‏⁠]", "", text)
    text = _HEADER_RE.sub("", text)
    # Filter noise lines BEFORE merging Korean words
    lines: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            continue
        if any(p.match(line) for p in _NOISE_LINE_PATTERNS):
            continue
        lines.append(line)
    text = "\n".join(lines)
    # Now merge broken Korean words
    text = re.sub(r"([가-힣])\n([가-힣])", r"\1\2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0

    for pages_path in sorted(EXTRACT_DIR.glob("*/pages.jsonl")):
        sid = pages_path.parent.name
        src_out = OUT_DIR / sid
        src_out.mkdir(parents=True, exist_ok=True)
        out_path = src_out / "normalized.jsonl"
        count = 0

        with pages_path.open("r", encoding="utf-8") as src, \
             out_path.open("w", encoding="utf-8") as out:
            for line in src:
                if not line.strip():
                    continue
                row = json.loads(line)
                raw = str(row.get("raw_text", ""))
                cleaned = clean_text(raw)
                if not cleaned:
                    continue
                row["clean_text"] = cleaned
                row["section_type"] = classify_section(raw)
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
        total += count

    print(f"[normalizer_v2] normalized={total} → {OUT_DIR}/{{source_id}}/normalized.jsonl")


if __name__ == "__main__":
    main()
