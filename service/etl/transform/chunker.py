from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IN_PATH = ROOT / "data" / "transform" / "normalized" / "normalized.jsonl"
OUT_DIR = ROOT / "data" / "transform" / "final"

CHUNK_SIZE = 800   # 청크 최대 글자 수
OVERLAP = 150      # 앞 청크 마지막 N자를 다음 청크 앞에 붙임
MIN_CHUNK = 80     # 이보다 짧으면 청크 생략

# 발언자 마커: ◯위원장 김석기, ◯홍길동 위원 등
_SPEAKER_RE = re.compile(r"(?=◯)")
# 한국어 문장 끝 패턴
_SENT_END_RE = re.compile(r"(?<=[다요임까함됩니겠]\.)\s+|(?<=[.!?])\s+")


def _extract_speaker(segment: str) -> tuple[str, str]:
    """◯발언자명 텍스트 → (speaker, text) 분리"""
    m = re.match(r"◯([^\s　]{1,20}(?:\s[^\s　]{1,10})?)\s+(.*)", segment, re.DOTALL)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", segment.strip()


def _split_by_sentence(text: str, max_size: int) -> list[str]:
    """문장 경계에서 자르기. 그래도 넘으면 강제 분할."""
    if len(text) <= max_size:
        return [text]

    parts: list[str] = []
    buf = ""
    # 문장 경계로 분리 시도
    sentences = _SENT_END_RE.split(text)
    for sent in sentences:
        if len(buf) + len(sent) <= max_size:
            buf += sent + " "
        else:
            if buf.strip():
                parts.append(buf.strip())
            # 문장 자체가 max_size 초과 → 강제 분할
            while len(sent) > max_size:
                parts.append(sent[:max_size])
                sent = sent[max_size:]
            buf = sent + " "
    if buf.strip():
        parts.append(buf.strip())
    return parts or [text[:max_size]]


def _make_chunks(source_id: str, text: str, metadata: dict) -> list[dict]:
    """
    1. ◯ 마커로 발언자 단위 분리
    2. 발언이 길면 문장 경계에서 추가 분할
    3. 청크 간 overlap 추가
    """
    # ◯ 마커가 전혀 없으면 문장 경계 분할로 폴백
    segments = _SPEAKER_RE.split(text)
    # 첫 조각은 목차·헤더일 가능성 높음 — ◯ 없으면 발언자 없는 서문
    chunks: list[dict] = []
    prev_tail = ""  # overlap용 직전 청크 끝부분

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        speaker, body = _extract_speaker(seg)
        if not body:
            continue

        # 발언 단위를 문장 경계에서 추가 분할
        pieces = _split_by_sentence(body, CHUNK_SIZE)

        for piece in pieces:
            # overlap: 직전 청크 마지막 부분 앞에 붙이기
            content = (prev_tail + " " + piece).strip() if prev_tail else piece
            if len(content) < MIN_CHUNK:
                continue

            chunk_meta = dict(metadata)
            if speaker:
                chunk_meta["speaker"] = speaker  # 발언자 오버라이드

            chunks.append({
                "chunk_id": f"{source_id}_{len(chunks)}",
                "source_id": source_id,
                "content": content,
                "text": content,         # 하위 호환
                "speaker": speaker,
                "metadata": chunk_meta,
            })
            # 다음 청크 overlap용: 현재 조각 끝 OVERLAP자
            prev_tail = piece[-OVERLAP:] if len(piece) > OVERLAP else piece

    return chunks


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "chunks.jsonl"
    total = 0

    if not IN_PATH.exists():
        out_path.write_text("", encoding="utf-8")
        print(f"[chunker] no input: {IN_PATH}")
        return

    with IN_PATH.open("r", encoding="utf-8") as src, \
         out_path.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.strip():
                continue
            row = json.loads(line)
            chunks = _make_chunks(
                source_id=row.get("source_id", ""),
                text=str(row.get("text", "")),
                metadata=row.get("metadata", {}),
            )
            for chunk in chunks:
                out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            total += len(chunks)

    print(f"[chunker] chunks={total} -> {out_path}")


if __name__ == "__main__":
    main()
