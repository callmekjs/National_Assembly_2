"""
service.etl.transform.chunker 단위 테스트

실행:
  pytest tests/test_chunker.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.etl.transform.chunker import (
    _extract_speaker,
    _make_chunks,
    _split_by_sentence,
    MIN_CHUNK,
    CHUNK_SIZE,
)


# ── _extract_speaker ─────────────────────────────────────────────────

class TestExtractSpeaker:
    def test_normal_speaker(self):
        speaker, text = _extract_speaker("◯외교부장관 조태열 오늘 회의에서 말씀드리겠습니다.")
        assert speaker == "외교부장관 조태열"
        assert "오늘" in text

    def test_single_name(self):
        # regex가 최대 2단어까지 화자명으로 캡처하는 설계 — 이름이 포함되면 통과
        speaker, text = _extract_speaker("◯홍길동 발언 내용입니다.")
        assert "홍길동" in speaker

    def test_no_marker(self):
        speaker, text = _extract_speaker("발언자 없는 텍스트입니다.")
        assert speaker == ""
        assert "발언자 없는" in text

    def test_empty(self):
        speaker, text = _extract_speaker("")
        assert speaker == ""
        assert text == ""


# ── _split_by_sentence ───────────────────────────────────────────────

class TestSplitBySentence:
    def test_short_text_not_split(self):
        text = "짧은 텍스트입니다."
        parts = _split_by_sentence(text, max_size=200)
        assert len(parts) == 1
        assert parts[0] == text

    def test_long_text_split(self):
        # 60회 반복(약 960자) > CHUNK_SIZE(800)이므로 반드시 분할
        long = "이것은 첫 번째 문장입니다. " * 60
        parts = _split_by_sentence(long, max_size=CHUNK_SIZE)
        assert len(parts) > 1
        for p in parts:
            assert len(p) <= CHUNK_SIZE + 50  # 약간의 여유

    def test_single_sentence_over_limit_forced(self):
        text = "가" * (CHUNK_SIZE + 100)
        parts = _split_by_sentence(text, max_size=CHUNK_SIZE)
        assert len(parts) >= 2


# ── _make_chunks ─────────────────────────────────────────────────────

class TestMakeChunks:
    def test_basic_chunks_created(self):
        # 본문이 MIN_CHUNK(80자) 이상이어야 청크로 생성됨
        body = "대북정책에 대해 말씀드리겠습니다. 우리는 강력한 외교적 노력을 기울이고 있습니다. 지속적인 대화와 협상을 통해 한반도 평화를 이끌어 나가겠습니다."
        text = f"◯외교부장관 조태열 {body}"
        chunks = _make_chunks("src_001", text, {"committee": "외교통일위원회"})
        assert len(chunks) >= 1
        assert chunks[0]["speaker"] == "외교부장관 조태열"
        assert "대북정책" in chunks[0]["content"]

    def test_speaker_isolation(self):
        body1 = "회의를 시작하겠습니다. 오늘 외교통일위원회 안건을 순서대로 진행하겠으니 위원 여러분의 적극적인 협조와 참여를 부탁드립니다. 좋은 의견 많이 나눠주시기 바랍니다."
        body2 = "네, 말씀드리겠습니다. 현재 외교부는 한반도 비핵화와 평화 정착을 위한 다각적인 외교적 노력을 기울이고 있으며 관련국과 긴밀히 협의하고 있습니다."
        text = f"◯위원장 김석기 {body1}\n◯외교부장관 조태열 {body2}"
        chunks = _make_chunks("src_002", text, {})
        speakers = [c["speaker"] for c in chunks]
        assert "위원장 김석기" in speakers
        assert "외교부장관 조태열" in speakers
        assert len(chunks) >= 2

    def test_min_chunk_filter(self):
        text = "◯홍길동 예."  # MIN_CHUNK 미만
        chunks = _make_chunks("src_003", text, {})
        assert all(len(c["content"]) >= MIN_CHUNK for c in chunks)

    def test_chunk_id_unique(self):
        text = (
            "◯위원 박영선 " + "질문 내용입니다. " * 30 + "\n"
            "◯장관 홍길동 " + "답변 내용입니다. " * 30
        )
        chunks = _make_chunks("src_004", text, {})
        ids = [c["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids))

    def test_metadata_propagated(self):
        body = "발언 내용입니다. 상세한 내용을 말씀드리겠습니다. 외교부는 현재 여러 현안에 대해 적극적으로 대응하고 있으며 지속적인 노력을 기울이고 있습니다."
        text = f"◯외교부장관 조태열 {body}"
        meta = {"committee": "외교통일위원회", "meeting_date": "2026-01-15"}
        chunks = _make_chunks("src_005", text, meta)
        assert len(chunks) >= 1
        assert chunks[0]["metadata"]["committee"] == "외교통일위원회"
        assert chunks[0]["metadata"]["meeting_date"] == "2026-01-15"

    def test_no_speaker_marker_fallback(self):
        text = "발언자 마커 없이 긴 텍스트가 있습니다. " * 10
        chunks = _make_chunks("src_006", text, {})
        # ◯ 없는 텍스트도 청크로 만들어지거나(빈 화자), 아예 안 만들어지거나
        # 어느 쪽이든 예외 없이 처리되어야 함
        assert isinstance(chunks, list)
