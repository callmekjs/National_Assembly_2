from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EmbeddingModelType(str, Enum):
    MULTILINGUAL_E5_SMALL = "intfloat/multilingual-e5-small"
    MULTILINGUAL_E5_LARGE = "intfloat/multilingual-e5-large"
    BGE_M3 = "BAAI/bge-m3"


@dataclass
class ModelConfig:
    model_name: str
    display_name: str
    dimension: int
    max_seq_length: int
    batch_size: int
    normalize_embeddings: bool
    pooling_mode: str
    trust_remote_code: bool
    device: str = "cuda"
    extra_params: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


MODEL_CONFIGS: dict[EmbeddingModelType, ModelConfig] = {
    EmbeddingModelType.MULTILINGUAL_E5_SMALL: ModelConfig(
        model_name="intfloat/multilingual-e5-small",
        display_name="E5-Small (Multilingual)",
        dimension=384,
        max_seq_length=512,
        batch_size=64,
        normalize_embeddings=True,
        pooling_mode="mean",
        trust_remote_code=False,
        extra_params={"query_prefix": "query: ", "passage_prefix": "passage: ", "torch_dtype": "float32"},
        notes="범용 임베딩 모델",
    ),
    EmbeddingModelType.MULTILINGUAL_E5_LARGE: ModelConfig(
        model_name="intfloat/multilingual-e5-large",
        display_name="E5-Large (Multilingual)",
        dimension=1024,
        max_seq_length=512,
        batch_size=32,
        normalize_embeddings=True,
        pooling_mode="mean",
        trust_remote_code=False,
        extra_params={"query_prefix": "query: ", "passage_prefix": "passage: ", "torch_dtype": "float32"},
        notes="고품질 범용 임베딩 모델",
    ),
    EmbeddingModelType.BGE_M3: ModelConfig(
        model_name="BAAI/bge-m3",
        display_name="BGE-M3",
        dimension=1024,
        max_seq_length=8192,
        batch_size=12,
        normalize_embeddings=True,
        pooling_mode="cls",
        trust_remote_code=False,
        extra_params={},
        notes="최강 다국어 임베딩, Dense+Sparse 지원, 한국어 정치/법률 도메인 강함",
    ),
}


def get_model_config(model_type: EmbeddingModelType) -> ModelConfig:
    return MODEL_CONFIGS[model_type]
