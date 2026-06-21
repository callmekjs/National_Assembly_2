"""
데이터 품질 지표 추적 모듈
파이프라인 실행마다 청크 품질 현황을 측정하고 reports/ 에 저장한다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "reports"


def _percentile(sorted_vals: list[int], p: float) -> int:
    if not sorted_vals:
        return 0
    idx = int(len(sorted_vals) * p / 100)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def measure_chunks(path: Path) -> dict:
    lengths: list[int] = []
    speaker_ok = 0
    committee_ok = 0
    date_ok = 0

    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            content = row.get("content") or row.get("text", "")
            meta = row.get("metadata") or {}

            lengths.append(len(content))
            if row.get("speaker", "").strip():
                speaker_ok += 1
            if meta.get("committee", "").strip():
                committee_ok += 1
            if meta.get("meeting_date", "").strip():
                date_ok += 1

    n = len(lengths)
    if n == 0:
        return {"total": 0}

    lengths.sort()
    short_80  = sum(1 for l in lengths if l < 80)
    short_300 = sum(1 for l in lengths if l < 300)

    return {
        "total": n,
        "length": {
            "min": lengths[0],
            "max": lengths[-1],
            "avg": sum(lengths) // n,
            "p25": _percentile(lengths, 25),
            "p50": _percentile(lengths, 50),
            "p75": _percentile(lengths, 75),
        },
        "short_chunk": {
            "under_80":  {"count": short_80,  "pct": round(short_80  / n * 100, 1)},
            "under_300": {"count": short_300, "pct": round(short_300 / n * 100, 1)},
        },
        "fill_rate": {
            "speaker":      round(speaker_ok   / n * 100, 1),
            "committee":    round(committee_ok  / n * 100, 1),
            "meeting_date": round(date_ok       / n * 100, 1),
        },
    }


def measure_extracted(path: Path) -> dict:
    total = empty_text = short_text = missing_date = missing_committee = 0

    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            text = row.get("text", "")
            meta = row.get("metadata") or {}

            if not text:
                empty_text += 1
            elif len(text) < 100:
                short_text += 1
            if not meta.get("meeting_date", "").strip():
                missing_date += 1
            if not meta.get("committee", "").strip():
                missing_committee += 1

    return {
        "total": total,
        "empty_text": empty_text,
        "short_text_under_100": short_text,
        "missing_meeting_date": missing_date,
        "missing_committee": missing_committee,
    }


def run_report() -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = {
        "generated_at": now,
        "extract": measure_extracted(ROOT / "data/extract/extracted.jsonl"),
        "chunks":  measure_chunks(ROOT / "data/transform/final/chunks.jsonl"),
    }

    # 리포트 저장
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    fname = datetime.now().strftime("quality_%Y%m%d_%H%M%S.json")
    out_path = REPORT_DIR / fname
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_report(report, out_path)
    return report


def _print_report(r: dict, path: Path) -> None:
    ext = r["extract"]
    chk = r["chunks"]
    ln  = chk.get("length", {})
    fr  = chk.get("fill_rate", {})
    sc  = chk.get("short_chunk", {})

    print(f"[quality] {r['generated_at']}")
    print(f"  [extract] 총={ext['total']} 빈텍스트={ext['empty_text']} "
          f"짧은텍스트={ext['short_text_under_100']} "
          f"날짜누락={ext['missing_meeting_date']} 위원회누락={ext['missing_committee']}")
    print(f"  [chunks]  총={chk['total']}  avg={ln.get('avg')}자  "
          f"p50={ln.get('p50')}자  max={ln.get('max')}자")
    print(f"  [chunks]  300자미만={sc.get('under_300',{}).get('pct')}%  "
          f"speaker={fr.get('speaker')}%  "
          f"committee={fr.get('committee')}%  "
          f"meeting_date={fr.get('meeting_date')}%")
    print(f"  → 저장: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    run_report()
