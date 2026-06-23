"""
Notion 자동 동기화 스크립트 (요약 모드)
- 매 실행 시 Notion 페이지 맨 아래에 요약 블록을 추가합니다.
- CHANGELOG.md 최신 마일스톤 1개 + ROADMAP.md 미완료 항목만 올립니다.
- python notion_sync.py          → 즉시 1회 동기화
- python notion_sync.py --watch  → 파일 감시 모드
"""
import os
import re
import sys
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

TOKEN = os.environ.get("Notion", "")
PARENT_PAGE_ID = "3852fea7-737b-80fe-b096-d01a56dc03b4"
BASE_URL = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
ROOT = Path(__file__).parent
DONE_FILE = ROOT / "CHANGELOG.md"
TODO_FILE = ROOT / "ROADMAP.md"


# ── Notion 블록 빌더 ──────────────────────────────────────────────

def _rich(text: str, bold=False, code=False) -> dict:
    return {
        "type": "text",
        "text": {"content": text[:2000]},
        "annotations": {"bold": bold, "code": code,
                        "italic": False, "strikethrough": False,
                        "underline": False, "color": "default"},
    }

def h2(t): return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [_rich(t, bold=True)]}}
def h3(t): return {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [_rich(t)]}}
def para(t=""): return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [_rich(t)] if t else []}}
def todo(t, checked=False): return {"object": "block", "type": "to_do", "to_do": {"rich_text": [_rich(t)], "checked": checked}}
def bullet(t): return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_rich(t)]}}
def divider(): return {"object": "block", "type": "divider", "divider": {}}
def callout(t, emoji="📌"): return {"object": "block", "type": "callout", "callout": {"rich_text": [_rich(t)], "icon": {"type": "emoji", "emoji": emoji}}}


# ── 요약 추출 ─────────────────────────────────────────────────────

def extract_latest_done(path: Path) -> list:
    """CHANGELOG.md에서 가장 최신 ## [마일스톤] 섹션 1개만 추출."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^(?=## \[)", text)
    content_sections = [s for s in sections if s.startswith("## [")]
    if not content_sections:
        return []

    latest = content_sections[0]
    blocks = []
    for line in latest.splitlines():
        line = line.rstrip()
        if line.startswith("## "):
            blocks.append(h2(line[3:].strip()))
        elif line.startswith("### "):
            blocks.append(h3(line[4:].strip()))
        elif line.strip().startswith("- ") and not line.strip().startswith("- ["):
            blocks.append(bullet(line.strip()[2:].strip()))
        elif line.strip() == "" and blocks:
            pass  # 빈 줄은 Notion에서 자동 처리
        elif line.strip() and not line.startswith("#"):
            blocks.append(para(line.strip()))
    return blocks


def extract_pending_todos(path: Path) -> list:
    """ROADMAP.md에서 미완료 - [ ] 항목만 추출. 할 일 없는 빈 섹션 헤더는 제외."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")

    STOP_KEYWORDS = ("우선순위", "작성 규칙")

    blocks = []
    cur_h2: dict | None = None
    cur_h3: dict | None = None
    h2_emitted = False
    h3_emitted = False

    for line in text.splitlines():
        line = line.rstrip()
        stripped = line.strip()

        if line.startswith("## ") and any(k in line for k in STOP_KEYWORDS):
            break

        if line.startswith("## "):
            cur_h2 = h2(line[3:].strip())
            cur_h3 = None
            h2_emitted = False
            h3_emitted = False
        elif line.startswith("### "):
            cur_h3 = h3(line[4:].strip())
            h3_emitted = False
        elif stripped.startswith("- [ ] "):
            if cur_h2 and not h2_emitted:
                blocks.append(cur_h2)
                h2_emitted = True
            if cur_h3 and not h3_emitted:
                blocks.append(cur_h3)
                h3_emitted = True
            blocks.append(todo(stripped[6:].strip(), checked=False))

    return blocks


# ── Notion API 헬퍼 ───────────────────────────────────────────────

def _notion_request(method: str, url: str, **kwargs) -> requests.Response:
    for attempt in range(3):
        resp = requests.request(method, url, headers=HEADERS, **kwargs)
        if resp.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"[notion_sync] rate limited, {wait}s 후 재시도...")
            time.sleep(wait)
            continue
        return resp
    resp.raise_for_status()
    return resp

def append_blocks(page_id: str, blocks: list):
    for i in range(0, len(blocks), 100):
        resp = _notion_request(
            "PATCH",
            f"{BASE_URL}/blocks/{page_id}/children",
            json={"children": blocks[i:i+100]},
        )
        if not resp.ok:
            print(f"[ERROR] {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()


# ── 동기화 메인 로직 ─────────────────────────────────────────────

def sync():
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[notion_sync] 동기화 시작 {now}")

    blocks = []
    blocks.append(divider())
    blocks.append(callout(f"업데이트: {now}", "🕐"))

    # 오늘 한 것 (최신 섹션 1개)
    done_blocks = extract_latest_done(DONE_FILE)
    if done_blocks:
        blocks.append(h2("✅ 최근 완료 (CHANGELOG)"))
        blocks.extend(done_blocks)

    # 남은 할 일 (미완료만)
    todo_blocks = extract_pending_todos(TODO_FILE)
    if todo_blocks:
        blocks.append(h2("📋 남은 할 일 (ROADMAP)"))
        blocks.extend(todo_blocks)

    append_blocks(PARENT_PAGE_ID, blocks)
    url = f"https://www.notion.so/{PARENT_PAGE_ID.replace('-', '')}"
    print(f"[notion_sync] 완료! → {url}")
    return url


# ── 파일 감시 모드 ────────────────────────────────────────────────

def watch():
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    watch_names = {DONE_FILE.name, TODO_FILE.name}

    class Handler(FileSystemEventHandler):
        def __init__(self):
            self._last = 0

        def on_modified(self, event):
            if Path(event.src_path).name in watch_names:
                now = time.time()
                if now - self._last < 1:
                    return
                self._last = now
                print(f"\n[notion_sync] 변경 감지: {Path(event.src_path).name}")
                try:
                    sync()
                except Exception as e:
                    print(f"[ERROR] {e}")

    observer = Observer()
    observer.schedule(Handler(), path=str(ROOT), recursive=False)
    observer.start()
    print(f"[notion_sync] 감시 중... (Ctrl+C로 종료)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    print("[notion_sync] 종료")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        sync()
        watch()
    else:
        sync()
