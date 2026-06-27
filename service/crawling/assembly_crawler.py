"""국회 위원회 회의록 PDF 범용 수집기.

사용법:
    python -m service.crawling.assembly_crawler --committee 과학기술정보방송통신위원회
    python -m service.crawling.assembly_crawler --committee 정무위원회
    python -m service.crawling.assembly_crawler --list-committees
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]

_API_ENDPOINT = "https://www.assembly.go.kr/portal/cnts/cntsCmmit/listMtgRcord.json"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# 위원회별 menuNo (CSRF 발급 + API 라우팅 기준)
# 스크린샷 URL에서 확인: dataA.do?menuNo=600238 → 과학기술정보방송통신위원회
_COMMITTEE_MENU_NO: dict[str, str] = {
    "외교통일위원회":           "600045",   # 기존 검증된 값
    "과학기술정보방송통신위원회": "600238",   # 스크린샷 URL에서 확인
}
_FALLBACK_MENU_NO = "600045"   # 알 수 없는 위원회는 이 URL로 CSRF 발급

# committeeCd 탐색 범위 (22대 국회 상임위 코드 범위)
_CD_CANDIDATES = [f"9700{4 if i < 10 else ''}{i:02d}" for i in range(1, 25)]


def _csrf_url(menu_no: str) -> str:
    return f"https://www.assembly.go.kr/portal/main/contents.do?menuNo={menu_no}"


def _get_csrf(session: requests.Session, menu_no: str) -> str:
    url = _csrf_url(menu_no)
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    token = (soup.select_one("meta[name='_csrf']") or {}).get("content", "")
    if not token:
        # 일부 위원회 페이지는 main이 아닌 다른 경로 → fallback
        if menu_no != _FALLBACK_MENU_NO:
            return _get_csrf(session, _FALLBACK_MENU_NO)
        raise RuntimeError("CSRF 토큰 발급 실패. 네트워크를 확인하세요.")
    return token


def _query_api(
    session: requests.Session,
    csrf: str,
    menu_no: str,
    committee_cd: str = "",
    page_index: int = 1,
    title_keyword: str = "제22대",
) -> dict:
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
    resp = session.post(
        _API_ENDPOINT,
        data=payload,
        timeout=30,
        headers={"Referer": _csrf_url(menu_no)},
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_all_rows(
    session: requests.Session,
    csrf: str,
    menu_no: str,
    committee_cd: str,
    committee_keyword: str,
    title_keyword: str,
) -> list[dict]:
    """페이지 전체를 순회하며 위원회 이름이 일치하는 행만 반환."""
    all_rows: list[dict] = []
    page = 1
    while True:
        data = _query_api(session, csrf, menu_no, committee_cd, page, title_keyword)
        if data.get("resultCode") != "success":
            break
        rows = data.get("resultList") or []
        for row in rows:
            name = str(row.get("committeeName") or "")
            pdf_url = str(row.get("pdfLinkUrl") or "")
            if committee_keyword in name and pdf_url:
                all_rows.append(row)
        pg = data.get("paginationInfo") or {}
        if page >= int(pg.get("totalPageCount") or 1):
            break
        page += 1
    return all_rows


def discover_committee_code(
    session: requests.Session,
    csrf: str,
    menu_no: str,
    committee_keyword: str,
) -> str | None:
    """committeeCd를 자동 탐색 (menuNo 단독 라우팅이 안 될 때 사용)."""
    print(f"[discover] '{committee_keyword}' committeeCd 탐색 중 ({len(_CD_CANDIDATES)}개 후보)...")
    for cd in _CD_CANDIDATES:
        try:
            data = _query_api(session, csrf, menu_no, committee_cd=cd, page_index=1)
            for row in (data.get("resultList") or []):
                if committee_keyword in str(row.get("committeeName") or ""):
                    print(f"[discover] 발견: committeeCd={cd}")
                    return cd
            time.sleep(0.25)
        except Exception:
            continue
    return None


def list_all_committees(session: requests.Session) -> None:
    """탐색 범위 내 위원회 목록을 출력."""
    menu_no = _FALLBACK_MENU_NO
    csrf = _get_csrf(session, menu_no)
    found: dict[str, str] = {}
    print("[탐색 중] 잠시 기다려 주세요...")
    for cd in _CD_CANDIDATES:
        try:
            data = _query_api(session, csrf, menu_no, committee_cd=cd)
            for row in (data.get("resultList") or []):
                name = str(row.get("committeeName") or "")
                if name and name not in found:
                    found[name] = cd
            time.sleep(0.2)
        except Exception:
            continue
    print("\n[위원회 목록]")
    for name, cd in sorted(found.items()):
        print(f"  {name:30s}  committeeCd={cd}")


def _extract_id(pdf_url: str) -> str:
    qs = parse_qs(urlparse(pdf_url).query)
    return (qs.get("id") or [""])[0]


def _build_filename(row: dict, idx: int) -> str:
    date = str(row.get("confDate") or "").replace("-", "")
    num = re.sub(r"[^\w\-가-힣]", "_", str(row.get("conferNum") or "")).strip("_")
    mid = _extract_id(str(row.get("pdfLinkUrl") or ""))
    if date and num and mid:
        return f"{date}_{num}_{mid}.pdf"
    if date and mid:
        return f"{date}_{mid}.pdf"
    return f"minutes_{idx:04d}.pdf"


def _download_pdf(session: requests.Session, url: str, target: Path) -> bool:
    with session.get(url, timeout=60, stream=True) as resp:
        resp.raise_for_status()
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "pdf" not in ct and ".pdf" not in url.lower():
            return False
        with target.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if chunk:
                    f.write(chunk)
    return True


def _load_log(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _save_log(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def download_committee(
    committee_name: str,
    title_keyword: str = "제22대",
    max_files: int | None = None,
    committee_cd: str = "",
) -> None:
    """위원회 이름으로 22대 국회 회의록 PDF를 수집."""
    out_dir = ROOT / "incoming_data" / committee_name
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "download_log.json"
    download_log = _load_log(log_path)

    session = requests.Session()
    session.headers["User-Agent"] = _USER_AGENT

    # 위원회 keyword: 이름의 앞 5글자 (API 결과 이름 비교용)
    keyword = committee_name[:5]
    menu_no = _COMMITTEE_MENU_NO.get(committee_name, _FALLBACK_MENU_NO)

    print(f"\n{'='*60}")
    print(f"[crawl] {committee_name}  (menuNo={menu_no})")
    print(f"[crawl] 저장 위치: {out_dir}")
    print(f"[crawl] 대상: {title_keyword} 회의록 전체")

    csrf = _get_csrf(session, menu_no)

    # 1차: menuNo만으로 조회 (committeecd= 빈 값 — 스크린샷 URL과 동일)
    rows = _fetch_all_rows(session, csrf, menu_no, committee_cd="", committee_keyword=keyword, title_keyword=title_keyword)

    # 2차: menuNo 단독 조회 실패 시 committeeCd 탐색
    if not rows:
        print(f"[crawl] menuNo 단독 조회 결과 없음 → committeeCd 자동 탐색")
        cd = committee_cd or discover_committee_code(session, csrf, menu_no, keyword)
        csrf = _get_csrf(session, menu_no)   # 탐색 후 재발급
        if cd:
            rows = _fetch_all_rows(session, csrf, menu_no, cd, keyword, title_keyword)
        if not rows:
            print(f"[crawl] 회의록을 찾지 못했습니다. 위원회명이나 menuNo를 확인해 주세요.")
            return

    targets = rows if max_files is None else rows[:max_files]
    print(f"[crawl] {len(rows)}건 발견 → {len(targets)}건 다운로드")

    saved = skipped = failed = 0
    for idx, row in enumerate(targets, 1):
        pdf_url = str(row.get("pdfLinkUrl") or "")
        mid = _extract_id(pdf_url)
        fname = _build_filename(row, idx)
        target = out_dir / fname

        if (mid and mid in download_log) or target.exists():
            skipped += 1
            print(f"  [skip] {fname}")
            continue
        try:
            if _download_pdf(session, pdf_url, target):
                saved += 1
                if mid:
                    download_log[mid] = {
                        "filename": fname,
                        "conf_date": str(row.get("confDate") or ""),
                        "title": str(row.get("title") or ""),
                    }
                print(f"  [save] {fname}")
            else:
                failed += 1
                print(f"  [fail] {pdf_url} (PDF 아님)")
        except Exception as e:
            failed += 1
            print(f"  [fail] {pdf_url} ({e})")

    _save_log(log_path, download_log)
    print(f"\n[crawl] 완료 ─ 저장:{saved} / 스킵:{skipped} / 실패:{failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description="국회 위원회 회의록 PDF 수집기 (22대)")
    parser.add_argument("--committee", help="위원회 이름 (예: 과학기술정보방송통신위원회)")
    parser.add_argument("--committee-cd", default="", help="committeeCd 직접 지정 (탐색 실패 시)")
    parser.add_argument("--title-keyword", default="제22대", help="회의명 필터 키워드")
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--list-committees", action="store_true", help="탐색 가능한 위원회 목록 출력")
    args = parser.parse_args()

    if args.list_committees:
        session = requests.Session()
        session.headers["User-Agent"] = _USER_AGENT
        list_all_committees(session)
        return

    if not args.committee:
        parser.print_help()
        return

    download_committee(
        committee_name=args.committee,
        title_keyword=args.title_keyword,
        max_files=args.max_files,
        committee_cd=args.committee_cd,
    )


if __name__ == "__main__":
    main()
