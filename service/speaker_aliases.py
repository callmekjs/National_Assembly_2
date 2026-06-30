from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIAS_PATH = ROOT / "data" / "speaker_aliases.json"

DEFAULT_SPEAKER_ALIASES: dict[str, str] = {
    "柳榮夏": "유영하",
    "柳榮夏": "유영하",
    "李憲昇": "이헌승",
    "李憲昇": "이헌승",
}

HANJA_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_SPEAKER_MARKER_RE = re.compile(
    r"(?:^|\n|[\s)])\s*[○◯]\s*"
    r"(?P<speaker>[가-힣\u3400-\u9fff\uf900-\ufaff]{2,4})\s*"
    r"(?P<role>위원장|위원|의원|장관|차관|총장|원장|대표|의장|후보자|후보)"
)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def _alias_keys(value: str) -> set[str]:
    raw = _compact(value)
    normalized = _compact(unicodedata.normalize("NFKC", raw))
    return {key for key in (raw, normalized) if key}


@lru_cache(maxsize=1)
def load_speaker_aliases() -> dict[str, str]:
    aliases = dict(DEFAULT_SPEAKER_ALIASES)
    try:
        if ALIAS_PATH.exists():
            with ALIAS_PATH.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                aliases.update({str(k): str(v) for k, v in raw.items()})
    except Exception:
        pass

    indexed: dict[str, str] = {}
    for key, value in aliases.items():
        for alias_key in _alias_keys(key):
            indexed[alias_key] = value.strip()
    return indexed


def normalize_speaker_name(speaker: str | None) -> str:
    raw = str(speaker or "").strip()
    if not raw:
        return ""
    aliases = load_speaker_aliases()
    for key in _alias_keys(raw):
        if key in aliases:
            return aliases[key]
    return raw


def normalize_speaker_aliases_in_text(text: str | None) -> str:
    out = str(text or "")
    aliases = load_speaker_aliases()
    for alias, normalized in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if alias and alias in out:
            out = out.replace(alias, normalized)
    return out


def speaker_alias_variants(speaker: str | None) -> list[str]:
    """표준 발언자명으로 검색할 때 사용할 원문/호환 한자 별칭 목록."""
    raw = str(speaker or "").strip()
    normalized = normalize_speaker_name(raw)
    values: set[str] = set()
    for value in (raw, normalized):
        if value:
            values.add(value)

    aliases = load_speaker_aliases()
    for alias, target in aliases.items():
        if normalize_speaker_name(target) == normalized:
            values.add(alias)
            values.update(_alias_keys(alias))

    return sorted(values, key=lambda item: (item != normalized, -len(item), item))


def has_hanja(value: str | None) -> bool:
    return bool(HANJA_RE.search(str(value or "")))


def extract_speaker_marker(text: str | None) -> tuple[str, str, str]:
    """본문의 '◯홍길동 위원' 표기에서 (표준명, 직함, 원문명)을 추출."""
    head = str(text or "")[:500]
    if not head:
        return "", "", ""
    match = _SPEAKER_MARKER_RE.search(head)
    if not match:
        return "", "", ""
    raw = match.group("speaker").strip()
    role = match.group("role").strip()
    normalized = normalize_speaker_name(raw)
    original = raw if raw and raw != normalized and has_hanja(raw) else ""
    return normalized, role, original


def normalize_speaker_record(record: dict) -> dict:
    out = dict(record)
    raw = str(out.get("speaker") or "").strip()
    normalized = normalize_speaker_name(raw)
    if normalized:
        out["speaker"] = normalized
    if raw and raw != normalized and has_hanja(raw):
        out.setdefault("speaker_original", raw)
        meta = dict(out.get("metadata") or {})
        meta.setdefault("speaker_original", raw)
        out["metadata"] = meta
    return out
