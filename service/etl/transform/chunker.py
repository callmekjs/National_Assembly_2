from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IN_PATH = ROOT / "data" / "transform" / "normalized" / "normalized.jsonl"
OUT_DIR = ROOT / "data" / "transform" / "final"
CHUNK_SIZE = 800


def _split_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size) if text[i : i + size].strip()]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "chunks.jsonl"
    count = 0
    if not IN_PATH.exists():
        out_path.write_text("", encoding="utf-8")
        print(f"[chunker] no input: {IN_PATH}")
        return

    with IN_PATH.open("r", encoding="utf-8") as src, out_path.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.strip():
                continue
            row = json.loads(line)
            source_id = row.get("source_id", "")
            metadata = row.get("metadata", {})
            for idx, piece in enumerate(_split_text(str(row.get("text", "")))):
                chunk = {
                    "chunk_id": f"{source_id}_{idx}",
                    "source_id": source_id,
                    "text": piece,
                    "metadata": metadata,
                }
                out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                count += 1
    print(f"[chunker] chunks={count} -> {out_path}")


if __name__ == "__main__":
    main()
