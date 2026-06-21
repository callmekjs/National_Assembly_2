from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IN_PATH = ROOT / "data" / "extract" / "extracted.jsonl"
OUT_DIR = ROOT / "data" / "transform" / "parser"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "parsed.jsonl"
    count = 0
    if not IN_PATH.exists():
        out_path.write_text("", encoding="utf-8")
        print(f"[parser] no input: {IN_PATH}")
        return

    with IN_PATH.open("r", encoding="utf-8") as src, out_path.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.strip():
                continue
            row = json.loads(line)
            text = str(row.get("text", "")).strip()
            if not text:
                continue
            parsed = {
                "chunk_id": f"{row.get('source_id', 'src')}_{count}",
                "source_id": row.get("source_id", ""),
                "text": text,
                "metadata": row.get("metadata", {}),
            }
            out.write(json.dumps(parsed, ensure_ascii=False) + "\n")
            count += 1
    print(f"[parser] parsed={count} -> {out_path}")


if __name__ == "__main__":
    main()
