from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TemporalInfo:
    years: list[int] = field(default_factory=list)
    quarters: list[int] = field(default_factory=list)
    relative: str | None = None
    date_range: dict[str, str] | None = None
    filters: dict[str, str] = field(default_factory=dict)


class TemporalQueryParser:
    def parse(self, _query: str) -> TemporalInfo:
        return TemporalInfo()
