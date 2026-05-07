from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[3]
IN_DIR = ROOT / "incoming_data"
OUT_DIR = ROOT / "data" / "extract"


def _metadata_from_filename(path: Path) -> dict[str, str]:
    name = path.stem
    out = {"committee": "", "meeting_date": "", "speaker": "", "section": ""}
    date_match = re.match(r"^(\d{8})_", name)
    if date_match:
        d = date_match.group(1)
        out["meeting_date"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    if "외교통일" in str(path):
        out["committee"] = "외교통일위원회"
    return out


def _extract_speaker(text: str) -> str:
    # 회의록 발언 시작 패턴 예: "◯위원장 김석기", "◯김건 위원"
    for line in text.splitlines()[:120]:
        m = re.search(r"◯\s*([가-힣]{2,4})\s*(위원장|위원|장관|차관|의원)?", line)
        if m:
            return m.group(1)
    return ""


def _source_files() -> list[Path]:
    if not IN_DIR.exists():
        return []
    files: list[Path] = []
    for pattern in ("*.txt", "*.md", "*.json", "*.jsonl", "*.pdf"):
        files.extend(IN_DIR.rglob(pattern))
    return sorted(files)


def _load_text(path: Path) -> str:
    if path.suffix == ".pdf":
        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return "\n".join(pages)
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return str(payload.get("text") or payload.get("content") or "")
        return ""
    return path.read_text(encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "extracted.jsonl"
    count = 0
    with out_path.open("w", encoding="utf-8") as out:
        for path in _source_files():
            text = _load_text(path).strip()
            if not text:
                continue
            meta = _metadata_from_filename(path)
            if not meta["committee"] and "외교통일위원회" in text[:1500]:
                meta["committee"] = "외교통일위원회"
            meta["speaker"] = _extract_speaker(text)
            row = {
                "source_id": path.stem,
                "text": text,
                "metadata": {
                    "source_path": str(path.relative_to(ROOT)),
                    "committee": meta["committee"],
                    "meeting_date": meta["meeting_date"],
                    "speaker": meta["speaker"],
                    "section": meta["section"],
                },
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    print(f"[extractor] extracted={count} -> {out_path}")


if __name__ == "__main__":
    main()
