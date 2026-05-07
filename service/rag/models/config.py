from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EmbeddingModelType(str, Enum):
    MULTILINGUAL_E5_SMALL = "intfloat/multilingual-e5-small"


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
    )
}


def get_model_config(model_type: EmbeddingModelType) -> ModelConfig:
    return MODEL_CONFIGS[model_type]
