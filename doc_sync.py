"""
문서 자동 동기화 스크립트

ROADMAP.md의 [ ] → [x] 변경을 감지해 오늘 dev-log에 기록하고,
eval JSON이 생성/변경되면 EVALUATION.md 최신 지표 블록을 갱신합니다.

    python doc_sync.py           # 1회 실행 (초기 스냅샷 + 갱신)
    python doc_sync.py --watch   # 파일 감시 모드 (권장)
    python doc_sync.py --eval    # EVALUATION.md만 갱신
    python doc_sync.py --devlog  # dev-log만 (현재 완료 항목 출력)
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent
ROADMAP_FILE    = ROOT / "ROADMAP.md"
EVALUATION_FILE = ROOT / "EVALUATION.md"
ARCHITECTURE_FILE = ROOT / "ARCHITECTURE.md"
DEVLOG_DIR      = ROOT / "docs" / "dev-log"
EVAL_REPORT_DIR = ROOT / "service" / "rag"
REPORT_DIR      = ROOT / "data" / "reports"
GRAPH_NODES_DIR = ROOT / "graph" / "nodes"

TODAY = date.today().isoformat()          # "2026-06-22"
DEVLOG_TODAY = DEVLOG_DIR / f"{TODAY}.md"

EVAL_AUTO_START = "<!-- EVAL_AUTO_START -->"
EVAL_AUTO_END   = "<!-- EVAL_AUTO_END -->"
ARCH_AUTO_START = "<!-- ARCH_NODES_START -->"
ARCH_AUTO_END   = "<!-- ARCH_NODES_END -->"


# ── ROADMAP 파싱 ──────────────────────────────────────────────────

def _parse_items(text: str) -> dict[str, bool]:
    """체크박스 전체 파싱. {항목 텍스트: 완료 여부}"""
    items: dict[str, bool] = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- [x] ") or s.startswith("- [X] "):
            items[s[6:].strip()] = True
        elif s.startswith("- [ ] "):
            items[s[6:].strip()] = False
    return items


def _newly_completed(prev: dict[str, bool], curr: dict[str, bool]) -> list[str]:
    return [t for t, done in curr.items() if done and not prev.get(t, False)]


def _section_of(item_text: str, roadmap_text: str) -> str:
    """항목이 속한 ## 섹션 제목 반환."""
    section = ""
    for line in roadmap_text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        s = line.strip()
        for prefix in ("- [x] ", "- [X] ", "- [ ] "):
            if s.startswith(prefix) and s[6:].strip() == item_text:
                return section
    return "기타"


# ── dev-log 업데이트 ──────────────────────────────────────────────

def update_devlog(newly: list[str], roadmap_text: str) -> None:
    if not newly:
        return

    DEVLOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%H:%M")

    lines: list[str] = []
    if not DEVLOG_TODAY.exists():
        lines.append(f"# 개발 일지 {TODAY}\n")

    lines.append(f"\n## {TODAY} {now} — 완료 ({len(newly)}건)\n")

    # 섹션별 그룹
    by_section: dict[str, list[str]] = {}
    for item in newly:
        sec = _section_of(item, roadmap_text)
        by_section.setdefault(sec, []).append(item)

    for sec, items in by_section.items():
        lines.append(f"\n### {sec}\n")
        for item in items:
            lines.append(f"- [x] {item}")

    lines.append("\n\n---\n")

    with DEVLOG_TODAY.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[doc_sync] dev-log 갱신 → {DEVLOG_TODAY.name} ({len(newly)}건)")
    for item in newly:
        print(f"  ✓ {item[:70]}")


# ── EVALUATION.md 업데이트 ───────────────────────────────────────

def _latest(glob: str, directory: Path) -> Path | None:
    files = sorted(directory.glob(glob), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _build_eval_block(eval_p: Path, quality_p: Path | None, ragas_p: Path | None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [EVAL_AUTO_START, f"\n> 🤖 자동 갱신: {now} | 파일: `{eval_p.name}`\n"]

    # 검색 회귀 테이블
    try:
        d = json.loads(eval_p.read_text(encoding="utf-8"))
        score = d.get("score_percent", "—")
        r3    = d.get("recall@3", "—")
        mrr   = d.get("mrr@3", "—")
        total = d.get("total_queries", "—")
        passed = d.get("passed", "—")
        lines += [
            "\n### 최신 검색 회귀\n",
            "| score% | recall@3 | mrr@3 | 통과 |",
            "|--------|----------|-------|------|",
            f"| **{score}** | **{r3}** | **{mrr}** | {passed}/{total} |",
        ]
        per_type = d.get("per_type", {})
        if per_type:
            lines += [
                "\n| 유형 | score% | recall@3 | mrr@3 |",
                "|------|--------|----------|-------|",
            ]
            for t, v in per_type.items():
                lines.append(
                    f"| {t} | {v.get('score_percent','—')} | {v.get('recall@3','—')} | {v.get('mrr@3','—')} |"
                )
    except Exception as e:
        lines.append(f"\n> eval 파싱 실패: {e}")

    # 데이터 품질
    if quality_p:
        try:
            q = json.loads(quality_p.read_text(encoding="utf-8"))
            c = q.get("chunks", {})
            fr = c.get("fill_rate", {})
            lines += [
                f"\n### 최신 데이터 품질 (`{quality_p.name}`)\n",
                "| 항목 | 값 |",
                "|------|----|",
                f"| 청크 수 | {c.get('total','—')} |",
                f"| 평균 청크 길이 | {c.get('length',{}).get('avg','—')}자 |",
                f"| speaker 채움률 | {fr.get('speaker','—')}% |",
                f"| committee·date | {fr.get('committee','—')}% / {fr.get('meeting_date','—')}% |",
            ]
        except Exception:
            pass

    # RAGAS
    if ragas_p:
        try:
            r = json.loads(ragas_p.read_text(encoding="utf-8"))
            res = r.get("results", r)
            if isinstance(res, dict):
                lines += [
                    f"\n### 최신 RAGAS (`{ragas_p.name}`)\n",
                    "| faithfulness | answer_relevancy | context_precision | context_recall |",
                    "|---|---|---|---|",
                    f"| {res.get('faithfulness','—')} | {res.get('answer_relevancy','—')} | {res.get('context_precision','—')} | {res.get('context_recall','—')} |",
                ]
        except Exception:
            pass

    lines.append(f"\n{EVAL_AUTO_END}")
    return "\n".join(lines)


def update_evaluation_md() -> bool:
    if not EVALUATION_FILE.exists():
        print("[doc_sync] EVALUATION.md 없음, 건너뜀")
        return False

    eval_p = _latest("eval_report_*.json", EVAL_REPORT_DIR)
    if not eval_p:
        print("[doc_sync] eval_report JSON 없음, 건너뜀")
        return False

    quality_p = _latest("quality_*.json", REPORT_DIR)
    ragas_p   = _latest("ragas_*.json", REPORT_DIR)

    block = _build_eval_block(eval_p, quality_p, ragas_p)
    text  = EVALUATION_FILE.read_text(encoding="utf-8")

    if EVAL_AUTO_START in text:
        updated = re.sub(
            re.escape(EVAL_AUTO_START) + r".*?" + re.escape(EVAL_AUTO_END),
            block,
            text,
            flags=re.DOTALL,
        )
    else:
        # 최초: "## 핵심 지표 요약" 바로 아래 삽입
        marker = "## 핵심 지표 요약\n"
        updated = text.replace(marker, f"{marker}\n{block}\n", 1)

    if updated == text:
        print("[doc_sync] EVALUATION.md 변경 없음")
        return False

    EVALUATION_FILE.write_text(updated, encoding="utf-8")
    print(f"[doc_sync] EVALUATION.md 갱신 ({eval_p.name})")
    return True


# ── ARCHITECTURE.md 업데이트 ─────────────────────────────────────

_NODE_ORDER = [
    "router", "query_rewrite", "retrieve", "rerank",
    "context_trim", "generate", "grounding_check", "guardrail", "answer",
]
_NODE_LABEL = {
    "router": "Router",
    "query_rewrite": "QueryRewrite",
    "retrieve": "Retrieve",
    "rerank": "Rerank",
    "context_trim": "ContextTrim",
    "generate": "Generate",
    "grounding_check": "GroundingCheck",
    "guardrail": "Guardrail",
    "answer": "Answer",
}
_NODE_FALLBACK = {
    "router": "검색 meta 기본값 병합 (`top_k`, `alpha`, …)",
    "query_rewrite": "질의 재작성 (현재 pass-through)",
    "retrieve": "pgvector 하이브리드 검색",
    "rerank": "후보 재정렬",
    "context_trim": "LLM 입력 토큰에 맞게 컨텍스트 자르기",
    "generate": "LLM 답변 (또는 `skip_generate`로 UI 스트리밍 위임)",
    "grounding_check": "문장 단위 `[n]` 인용 비율 측정 → FULL/PARTIAL/NONE + 경고 삽입",
    "guardrail": "면책 문구 삽입",
    "answer": "인용·최종 답변 정규화",
}


def _extract_node_desc(path: Path) -> str:
    """모듈 docstring 첫 줄(비어 있으면 파일명) 반환."""
    try:
        src = path.read_text(encoding="utf-8")
        m = re.match(r'"""(.*?)"""', src, re.DOTALL)
        if m:
            first = m.group(1).strip().splitlines()[0].strip()
            if first:
                return first
    except Exception:
        pass
    return path.stem


def _build_arch_block() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [ARCH_AUTO_START, f"\n> 🤖 자동 갱신: {now}\n",
             "\n| 노드 | 역할 |", "|------|------|"]

    for stem in _NODE_ORDER:
        p = GRAPH_NODES_DIR / f"{stem}.py"
        label = _NODE_LABEL.get(stem, stem)
        # fallback dict 우선 (9개 알려진 노드). 미등록 노드는 docstring 사용
        if stem in _NODE_FALLBACK:
            desc = _NODE_FALLBACK[stem]
        elif p.exists():
            desc = _extract_node_desc(p)
        else:
            desc = "—"
        lines.append(f"| {label} | {desc} |")

    lines.append(f"\n{ARCH_AUTO_END}")
    return "\n".join(lines)


def update_architecture_md() -> bool:
    if not ARCHITECTURE_FILE.exists():
        print("[doc_sync] ARCHITECTURE.md 없음, 건너뜀")
        return False
    if not GRAPH_NODES_DIR.exists():
        print("[doc_sync] graph/nodes/ 없음, 건너뜀")
        return False

    block = _build_arch_block()
    text = ARCHITECTURE_FILE.read_text(encoding="utf-8")

    if ARCH_AUTO_START in text:
        updated = re.sub(
            re.escape(ARCH_AUTO_START) + r".*?" + re.escape(ARCH_AUTO_END),
            block,
            text,
            flags=re.DOTALL,
        )
    else:
        # 최초: "## LangGraph RAG 파이프라인" 바로 아래 삽입
        marker = "## LangGraph RAG 파이프라인\n"
        updated = text.replace(marker, f"{marker}\n{block}\n", 1)

    if updated == text:
        print("[doc_sync] ARCHITECTURE.md 변경 없음")
        return False

    ARCHITECTURE_FILE.write_text(updated, encoding="utf-8")
    print("[doc_sync] ARCHITECTURE.md 갱신 (노드 테이블)")
    return True


# ── 1회 실행 ─────────────────────────────────────────────────────

def sync(prev_items: dict[str, bool] | None = None) -> dict[str, bool]:
    update_evaluation_md()
    update_architecture_md()

    if not ROADMAP_FILE.exists():
        return {}
    text = ROADMAP_FILE.read_text(encoding="utf-8")
    curr = _parse_items(text)

    if prev_items is not None:
        newly = _newly_completed(prev_items, curr)
        update_devlog(newly, text)
    else:
        done_count = sum(v for v in curr.values())
        total = len(curr)
        print(f"[doc_sync] 초기 스냅샷: {done_count}/{total}개 완료")

    return curr


# ── 감시 모드 ─────────────────────────────────────────────────────

def watch() -> None:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    roadmap_text = ROADMAP_FILE.read_text(encoding="utf-8") if ROADMAP_FILE.exists() else ""
    state = {"items": _parse_items(roadmap_text)}

    class Handler(FileSystemEventHandler):
        def __init__(self):
            self._last: dict[str, float] = {}

        def on_modified(self, event):
            p = Path(event.src_path)
            now = time.time()
            if now - self._last.get(str(p), 0) < 1.5:
                return
            self._last[str(p)] = now

            if p.name == ROADMAP_FILE.name:
                print(f"\n[doc_sync] ROADMAP.md 변경 감지")
                try:
                    text = ROADMAP_FILE.read_text(encoding="utf-8")
                    curr = _parse_items(text)
                    newly = _newly_completed(state["items"], curr)
                    update_devlog(newly, text)
                    if not newly:
                        print("[doc_sync] 새로 완료된 항목 없음")
                    state["items"] = curr
                except Exception as e:
                    print(f"[doc_sync] ERROR: {e}")

            elif p.suffix == ".json" and any(
                k in p.name for k in ("eval_report", "quality", "ragas")
            ):
                print(f"\n[doc_sync] {p.name} 변경 감지")
                try:
                    update_evaluation_md()
                except Exception as e:
                    print(f"[doc_sync] ERROR: {e}")

            elif p.suffix == ".py" and p.parent == GRAPH_NODES_DIR:
                print(f"\n[doc_sync] graph/nodes/{p.name} 변경 감지")
                try:
                    update_architecture_md()
                except Exception as e:
                    print(f"[doc_sync] ERROR: {e}")

    observer = Observer()
    observer.schedule(Handler(), path=str(ROOT), recursive=False)
    observer.schedule(Handler(), path=str(EVAL_REPORT_DIR), recursive=False)
    if REPORT_DIR.exists():
        observer.schedule(Handler(), path=str(REPORT_DIR), recursive=False)
    if GRAPH_NODES_DIR.exists():
        observer.schedule(Handler(), path=str(GRAPH_NODES_DIR), recursive=False)

    observer.start()
    print(f"[doc_sync] 감시 중... (Ctrl+C 종료)")
    print(f"  · ROADMAP.md        → {DEVLOG_TODAY.name}")
    print(f"  · eval JSON         → EVALUATION.md")
    print(f"  · graph/nodes/*.py  → ARCHITECTURE.md")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    print("[doc_sync] 종료")


# ── 진입점 ───────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--watch" in args:
        prev = sync()       # 초기 스냅샷
        watch()
    elif "--eval" in args:
        update_evaluation_md()
    elif "--arch" in args:
        update_architecture_md()
    elif "--devlog" in args:
        sync()
    else:
        sync()
