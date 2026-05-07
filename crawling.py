from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_SOURCE_URL = "https://www.assembly.go.kr/portal/main/contents.do?menuNo=600045"
DEFAULT_OUT_DIR = Path("incoming_data") / "외교통일위원회"
DEFAULT_MENU_NO = "600045"
DEFAULT_COMMITTEE_CD = "9700409"  # 외교통일위원회
DEFAULT_TITLE_KEYWORD = "제22대"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def get_csrf_token(session: requests.Session, source_url: str) -> str:
    resp = session.get(source_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    token = (soup.select_one("meta[name='_csrf']") or {}).get("content", "")
    if not token:
        raise RuntimeError("CSRF 토큰을 찾지 못했습니다.")
    return token


def extract_minutes_id(pdf_url: str) -> str:
    qs = parse_qs(urlparse(pdf_url).query)
    return (qs.get("id") or [""])[0]


def discover_pdf_rows(
    session: requests.Session,
    source_url: str,
    menu_no: str,
    committee_cd: str,
    title_keyword: str,
) -> list[dict]:
    csrf = get_csrf_token(session, source_url)
    endpoint = "https://www.assembly.go.kr/portal/cnts/cntsCmmit/listMtgRcord.json"
    page_index = 1
    all_rows: list[dict] = []

    while True:
        payload = {
            "menuNo": menu_no,
            "pageIndex": str(page_index),
            "cntsDivCd": "CMMIT",
            "committeeCd": committee_cd,
            "title": title_keyword,
            "beginDate": "",
            "endDate": "",
            "_csrf": csrf,
        }
        resp = session.post(endpoint, data=payload, timeout=30, headers={"Referer": source_url})
        resp.raise_for_status()
        data = resp.json()
        if data.get("resultCode") != "success":
            raise RuntimeError(f"회의록 목록 조회 실패: {data.get('msg')}")

        rows = data.get("resultList") or []
        if not rows:
            break
        all_rows.extend(rows)

        page_info = data.get("paginationInfo") or {}
        total_pages = int(page_info.get("totalPageCount") or 1)
        if page_index >= total_pages:
            break
        page_index += 1

    filtered: list[dict] = []
    for row in all_rows:
        title = str(row.get("title") or "")
        committee = str(row.get("committeeName") or "")
        pdf_link = str(row.get("pdfLinkUrl") or "")
        if "외교통일" not in committee:
            continue
        if title_keyword and title_keyword not in title:
            continue
        if not pdf_link:
            continue
        filtered.append(row)
    return filtered


def build_filename(row: dict, index: int) -> str:
    conf_date = str(row.get("confDate") or "").replace("-", "")
    conf_num = str(row.get("conferNum") or "")
    minutes_id = extract_minutes_id(str(row.get("pdfLinkUrl") or ""))
    safe_conf_num = re.sub(r"[^\w\-가-힣]", "_", conf_num).strip("_")
    if conf_date and safe_conf_num and minutes_id:
        return f"{conf_date}_{safe_conf_num}_{minutes_id}.pdf"
    if conf_date and minutes_id:
        return f"{conf_date}_{minutes_id}.pdf"
    return f"minutes_{index:04d}.pdf"


def download_pdf(session: requests.Session, url: str, target: Path) -> bool:
    with session.get(url, timeout=30, stream=True) as resp:
        resp.raise_for_status()
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "pdf" not in content_type and ".pdf" not in url.lower():
            return False
        with target.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
    return True


def _load_download_log(log_path: Path) -> dict[str, dict]:
    if not log_path.exists():
        return {}
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(k): v for k, v in payload.items() if isinstance(v, dict)}


def _save_download_log(log_path: Path, data: dict[str, dict]) -> None:
    log_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(
    source_url: str,
    out_dir: Path,
    menu_no: str,
    committee_cd: str,
    title_keyword: str,
    max_files: int | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "download_log.json"
    download_log = _load_download_log(log_path)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    rows = discover_pdf_rows(
        session=session,
        source_url=source_url,
        menu_no=menu_no,
        committee_cd=committee_cd,
        title_keyword=title_keyword,
    )
    if not rows:
        print("[crawling] 조건에 맞는 회의록을 찾지 못했습니다.")
        print(f"- committee_cd: {committee_cd}")
        print(f"- title_keyword: {title_keyword}")
        return

    targets = rows if max_files is None else rows[:max_files]
    saved = 0
    skipped = 0
    failed = 0

    for idx, row in enumerate(targets, start=1):
        pdf_url = str(row.get("pdfLinkUrl") or "")
        minutes_id = extract_minutes_id(pdf_url)
        filename = build_filename(row, idx)
        target = out_dir / filename
        if minutes_id and minutes_id in download_log:
            skipped += 1
            print(f"[skip] {target.name} (already logged: minutes_id={minutes_id})")
            continue
        if target.exists():
            skipped += 1
            print(f"[skip] {target.name} (already exists)")
            continue
        try:
            if download_pdf(session, pdf_url, target):
                saved += 1
                if minutes_id:
                    download_log[minutes_id] = {
                        "filename": target.name,
                        "pdf_url": pdf_url,
                        "conf_date": str(row.get("confDate") or ""),
                        "title": str(row.get("title") or ""),
                    }
                print(f"[save] {target.name}")
            else:
                failed += 1
                print(f"[fail] {pdf_url} (not a PDF response)")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[fail] {pdf_url} ({exc})")
    _save_download_log(log_path, download_log)

    print("\n[crawling] done")
    print(f"- source_url: {source_url}")
    print(f"- menu_no: {menu_no}")
    print(f"- committee_cd: {committee_cd}")
    print(f"- title_keyword: {title_keyword}")
    print(f"- discovered_rows: {len(rows)}")
    print(f"- target_max_files: {'ALL' if max_files is None else max_files}")
    print(f"- out_dir: {out_dir}")
    print(f"- download_log: {log_path}")
    print(f"- saved: {saved}")
    print(f"- skipped: {skipped}")
    print(f"- failed: {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="국회 위원회회의록 PDF 수집기")
    parser.add_argument("--url", default=DEFAULT_SOURCE_URL, help="위원회회의록 페이지 URL")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="다운로드 저장 폴더")
    parser.add_argument("--menu-no", default=DEFAULT_MENU_NO, help="국회 페이지 menuNo")
    parser.add_argument("--committee-cd", default=DEFAULT_COMMITTEE_CD, help="위원회 코드 (외교통일위원회=9700409)")
    parser.add_argument("--title-keyword", default=DEFAULT_TITLE_KEYWORD, help="회의명 필터 키워드")
    parser.add_argument("--max-files", type=int, default=None, help="최대 다운로드 개수 (기본: 전체)")
    args = parser.parse_args()
    run(
        source_url=args.url,
        out_dir=Path(args.out_dir),
        menu_no=args.menu_no,
        committee_cd=args.committee_cd,
        title_keyword=args.title_keyword,
        max_files=args.max_files,
    )


if __name__ == "__main__":
    main()
