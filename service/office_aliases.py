from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALIAS_PATH = ROOT / "data" / "office_aliases.json"


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = _compact(value)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value.strip())
    return out


@lru_cache(maxsize=1)
def load_office_aliases(path: str | None = None) -> dict[str, dict[str, Any]]:
    alias_path = Path(path) if path else DEFAULT_ALIAS_PATH
    if not alias_path.exists():
        return {}
    with alias_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        return {}
    return {
        str(key).strip(): value
        for key, value in raw.items()
        if str(key).strip() and isinstance(value, dict)
    }


def office_terms(office_key: str) -> list[str]:
    aliases = load_office_aliases()
    entry = aliases.get((office_key or "").strip())
    if not entry:
        return []
    return _dedupe(
        [office_key]
        + _as_list(entry.get("aliases"))
        + _as_list(entry.get("speaker_roles"))
    )


def office_keyword_terms(office_key: str) -> list[str]:
    aliases = load_office_aliases()
    entry = aliases.get((office_key or "").strip())
    if not entry:
        return office_terms(office_key)
    return _dedupe(office_terms(office_key) + _as_list(entry.get("agencies")))


def office_agencies(office_key: str) -> list[str]:
    entry = load_office_aliases().get((office_key or "").strip())
    return _dedupe(_as_list(entry.get("agencies")) if entry else [])


def office_position_types(office_key: str) -> list[str]:
    entry = load_office_aliases().get((office_key or "").strip())
    return _dedupe(_as_list(entry.get("position_types")) if entry else [])


def primary_speaker_role(office_key: str) -> str:
    entry = load_office_aliases().get((office_key or "").strip())
    if not entry:
        return (office_key or "").strip()
    roles = _as_list(entry.get("speaker_roles"))
    return roles[0] if roles else (office_key or "").strip()


def match_office_alias(text: str) -> str | None:
    compact_text = _compact(text)
    if not compact_text:
        return None
    candidates: list[tuple[int, str]] = []
    for office_key in load_office_aliases():
        for term in office_terms(office_key):
            compact_term = _compact(term)
            if compact_term and compact_term in compact_text:
                candidates.append((len(compact_term), office_key))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def office_query_metadata(office_key: str) -> dict[str, Any]:
    role = primary_speaker_role(office_key)
    return {
        "query_office_kw": office_key,
        "speaker_role": role,
        "office_terms": office_terms(office_key),
        "office_agencies": office_agencies(office_key),
        "office_position_types": office_position_types(office_key),
    }
