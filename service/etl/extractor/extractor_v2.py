from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[3]
IN_DIR = ROOT / "incoming_data"
OUT_DIR = ROOT / "data" / "v2" / "extract"


def _source_id(path: Path) -> str:
    return path.stem


def _file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _metadata_from_path(path: Path) -> dict:
    name = path.stem
    meeting_date = ""
    m = re.match(r"^(\d{8})_", name)
    if m:
        d = m.group(1)
        meeting_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    committee = "외교통일위원회" if "외교통일" in str(path) else ""
    return {"committee": committee, "meeting_date": meeting_date}


def extract_pages(path: Path) -> list[dict]:
    """PDF 1개 → 페이지별 raw_text 레코드 리스트."""
    source_id = _source_id(path)
    meta = _metadata_from_path(path)
    pages: list[dict] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            raw = page.extract_text() or ""
            if not raw.strip():
                continue
            pages.append({
                "source_id": source_id,
                "page_no": i,
                "raw_text": raw,
                "metadata": {
                    "committee": meta["committee"],
                    "meeting_date": meta["meeting_date"],
                    "source_path": str(path.relative_to(ROOT)),
                },
            })
    return pages


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_DIR / "source_manifest_v2.jsonl"
    pages_path = OUT_DIR / "pages_v2.jsonl"

    pdf_files = sorted(IN_DIR.rglob("*.pdf"))
    manifest_rows: list[dict] = []
    total_pages = 0

    with pages_path.open("w", encoding="utf-8") as pages_out:
        for path in pdf_files:
            pages = extract_pages(path)
            meta = _metadata_from_path(path)
            manifest_rows.append({
                "source_id": _source_id(path),
                "file_path": str(path.relative_to(ROOT)),
                "file_hash": _file_hash(path),
                "committee": meta["committee"],
                "meeting_date": meta["meeting_date"],
                "page_count": len(pages),
                "parser_version": "v2",
                "created_at": datetime.now().isoformat(),
            })
            for page in pages:
                pages_out.write(json.dumps(page, ensure_ascii=False) + "\n")
            total_pages += len(pages)

    with manifest_path.open("w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"[extractor_v2] sources={len(manifest_rows)} pages={total_pages}")
    print(f"  manifest → {manifest_path}")
    print(f"  pages   → {pages_path}")


if __name__ == "__main__":
    main()
