"""
파이프라인 실행 이력 추적
run_id 발급 → 단계별 지표 수집 → data/reports/run_history.jsonl 누적 저장
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY_FILE = ROOT / "data" / "reports" / "run_history.jsonl"


class PipelineRun:
    def __init__(self) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_id = f"{ts}_{uuid.uuid4().hex[:6]}"
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self._t0 = time.monotonic()
        self.stages: dict = {}
        self.contract_ok: bool | None = None
        self.quality: dict = {}

    # ── 단계별 지표 기록 ──────────────────────────────────────────

    def record_extract(self, total: int) -> None:
        self.stages["extract"] = {"total_docs": total}

    def record_transform(self, total: int) -> None:
        self.stages["transform"] = {"total_chunks": total}

    def record_embed(self, embedded: int, skipped: int) -> None:
        self.stages["embed"] = {"embedded": embedded, "skipped": skipped}

    def record_contract(self, ok: bool) -> None:
        self.contract_ok = ok

    def record_quality(self, report: dict) -> None:
        chk = report.get("chunks", {})
        ln = chk.get("length", {})
        fr = chk.get("fill_rate", {})
        self.quality = {
            "total_chunks": chk.get("total", 0),
            "avg_len": ln.get("avg"),
            "p50_len": ln.get("p50"),
            "speaker_fill_pct": fr.get("speaker"),
            "committee_fill_pct": fr.get("committee"),
            "date_fill_pct": fr.get("meeting_date"),
        }

    # ── 저장 ─────────────────────────────────────────────────────

    def save(self) -> dict:
        finished_at = datetime.now().isoformat(timespec="seconds")
        duration_sec = round(time.monotonic() - self._t0, 1)

        record = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "duration_sec": duration_sec,
            "stages": self.stages,
            "contract_ok": self.contract_ok,
            "quality": self.quality,
        }

        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        _print_run(record)
        return record


def _print_run(r: dict) -> None:
    chk = r["stages"].get("transform", {}).get("total_chunks", "?")
    emb = r["stages"].get("embed", {})
    q = r["quality"]
    print(
        f"[run:{r['run_id']}] "
        f"{r['started_at']} → {r['finished_at']} ({r['duration_sec']}s)  "
        f"chunks={chk}  "
        f"embedded={emb.get('embedded','?')} skip={emb.get('skipped','?')}  "
        f"contract={'OK' if r['contract_ok'] else 'NG' if r['contract_ok'] is False else '-'}  "
        f"speaker={q.get('speaker_fill_pct')}%"
    )


def load_history(n: int = 10) -> list[dict]:
    """최근 n개 실행 이력 반환"""
    if not HISTORY_FILE.exists():
        return []
    lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines[-n:] if l.strip()]


def print_history(n: int = 10) -> None:
    rows = load_history(n)
    if not rows:
        print("[run_tracker] 이력 없음")
        return
    print(f"[run_tracker] 최근 {len(rows)}건")
    for r in rows:
        _print_run(r)


if __name__ == "__main__":
    print_history()
