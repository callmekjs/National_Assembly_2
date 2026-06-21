"""
Notion 자동 동기화 스크립트
- 내가한거.md, 오늘내가할거.md 변경 시 자동으로 Notion 업데이트
- python notion_sync.py          → 즉시 1회 동기화
- python notion_sync.py --watch  → 파일 감시 모드 (파일 저장 시 자동 업데이트)
"""
import os
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
STATE_FILE = Path(__file__).parent / ".notion_sync_state.json"
ROOT = Path(__file__).parent
WATCH_FILES = [
    ROOT / "내가한거.md",
    ROOT / "오늘내가할거.md",
]

# ── Notion 블록 빌더 ──────────────────────────────────────────────

def _rich(text: str, bold=False, code=False) -> dict:
    return {
        "type": "text",
        "text": {"content": text[:2000]},
        "annotations": {"bold": bold, "code": code,
                        "italic": False, "strikethrough": False,
                        "underline": False, "color": "default"},
    }

def h1(t): return {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [_rich(t)]}}
def h2(t): return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [_rich(t)]}}
def h3(t): return {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [_rich(t)]}}
def para(t=""): return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [_rich(t)] if t else []}}
def todo(t, checked=False): return {"object": "block", "type": "to_do", "to_do": {"rich_text": [_rich(t)], "checked": checked}}
def bullet_item(t): return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_rich(t)]}}
def divider(): return {"object": "block", "type": "divider", "divider": {}}
def callout(t, emoji="📌"): return {"object": "block", "type": "callout", "callout": {"rich_text": [_rich(t)], "icon": {"type": "emoji", "emoji": emoji}}}
def code_block(t, lang="plain text"): return {"object": "block", "type": "code", "code": {"rich_text": [_rich(t[:2000])], "language": lang}}

# ── 마크다운 → Notion 블록 변환 ───────────────────────────────────

def md_to_blocks(md_text: str) -> list:
    blocks = []
    lines = md_text.splitlines()
    in_code = False
    code_lines = []
    code_lang = "plain text"

    for line in lines:
        # 코드 블록
        if line.startswith("```"):
            if not in_code:
                in_code = True
                lang = line[3:].strip()
                code_lang = lang if lang else "plain text"
                code_lines = []
            else:
                in_code = False
                blocks.append(code_block("\n".join(code_lines), code_lang))
            continue
        if in_code:
            code_lines.append(line)
            continue

        # 제목
        if line.startswith("#### "):
            blocks.append(h3(line[5:].strip()))
        elif line.startswith("### "):
            blocks.append(h3(line[4:].strip()))
        elif line.startswith("## "):
            blocks.append(h2(line[3:].strip()))
        elif line.startswith("# "):
            blocks.append(h1(line[2:].strip()))
        # 체크박스
        elif line.strip().startswith("- [x] ") or line.strip().startswith("- [X] "):
            blocks.append(todo(line.strip()[6:].strip(), checked=True))
        elif line.strip().startswith("- [ ] "):
            blocks.append(todo(line.strip()[6:].strip(), checked=False))
        # 구분선
        elif line.strip() in ("---", "***", "___"):
            blocks.append(divider())
        # 불릿
        elif line.strip().startswith("- ") or line.strip().startswith("* "):
            blocks.append(bullet_item(line.strip()[2:].strip()))
        # 빈 줄
        elif line.strip() == "":
            blocks.append(para())
        # 일반 텍스트
        else:
            blocks.append(para(line))

    return blocks

# ── Notion API 헬퍼 ───────────────────────────────────────────────

def _notion_request(method: str, url: str, **kwargs) -> requests.Response:
    """Notion API 호출 — 429 시 최대 3회 retry with backoff"""
    import time
    for attempt in range(3):
        resp = requests.request(method, url, headers=HEADERS, **kwargs)
        if resp.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"[notion_sync] rate limited, {wait}s 후 재시도 ({attempt+1}/3)...")
            time.sleep(wait)
            continue
        return resp
    resp.raise_for_status()
    return resp

def get_children(page_id: str) -> list:
    blocks = []
    url = f"{BASE_URL}/blocks/{page_id}/children?page_size=100"
    while url:
        resp = _notion_request("GET", url)
        resp.raise_for_status()
        data = resp.json()
        blocks.extend(data.get("results", []))
        url = f"{BASE_URL}/blocks/{page_id}/children?start_cursor={data['next_cursor']}&page_size=100" \
              if data.get("has_more") else None
    return blocks

def delete_block(block_id: str):
    _notion_request("DELETE", f"{BASE_URL}/blocks/{block_id}")

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

def create_page(parent_id: str, title: str) -> str:
    body = {
        "parent": {"page_id": parent_id},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
    }
    resp = _notion_request("POST", f"{BASE_URL}/pages", json=body)
    resp.raise_for_status()
    return resp.json()["id"]

def clear_page(page_id: str):
    children = get_children(page_id)
    for block in children:
        delete_block(block["id"])

def update_page_title(page_id: str, title: str):
    resp = _notion_request(
        "PATCH",
        f"{BASE_URL}/pages/{page_id}",
        json={"properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}}},
    )
    resp.raise_for_status()

# ── 상태 관리 (page_id 저장) ─────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

# ── 동기화 메인 로직 ─────────────────────────────────────────────

def sync():
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[notion_sync] 동기화 시작 {now}")

    # PARENT_PAGE_ID 에 직접 쓴다 (서브페이지 생성 없음)
    page_id = PARENT_PAGE_ID
    print(f"[notion_sync] 페이지 초기화 후 업데이트: {page_id}")
    clear_page(page_id)

    blocks = []
    blocks.append(callout(f"마지막 업데이트: {now}", "🕐"))
    blocks.append(divider())

    for md_file in WATCH_FILES:
        if not md_file.exists():
            print(f"[warn] 파일 없음: {md_file}")
            continue
        text = md_file.read_text(encoding="utf-8")
        file_blocks = md_to_blocks(text)
        blocks.extend(file_blocks)
        blocks.append(divider())

    append_blocks(page_id, blocks)
    url = f"https://www.notion.so/{page_id.replace('-', '')}"
    print(f"[notion_sync] 완료! → {url}")
    return url

# ── 파일 감시 모드 ────────────────────────────────────────────────

def watch():
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    watch_names = {f.name for f in WATCH_FILES}

    class Handler(FileSystemEventHandler):
        def __init__(self):
            self._last = 0

        def on_modified(self, event):
            if Path(event.src_path).name in watch_names:
                # 연속 저장 방지 (1초 내 중복 무시)
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
    print(f"  대상: {', '.join(f.name for f in WATCH_FILES)}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    print("[notion_sync] 종료")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        sync()  # 시작 시 1회 즉시 동기화
        watch()
    else:
        sync()
