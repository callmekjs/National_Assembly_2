from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        import torch
        from FlagEmbedding import BGEM3FlagModel
        use_fp16 = torch.cuda.is_available()
        _model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=use_fp16)
        logger.info("[BGE-M3] model loaded (fp16=%s)", use_fp16)
    return _model


def _to_float_dict(weights) -> dict[str, float]:
    return {k: float(v) for k, v in weights.items()}


def encode_dense(texts: list[str], batch_size: int = 12, max_length: int = 8192) -> list[list[float]]:
    out = _get_model().encode(texts, return_dense=True, return_sparse=False, batch_size=batch_size, max_length=max_length)
    return out["dense_vecs"].tolist()


def encode_sparse(texts: list[str], batch_size: int = 12) -> list[dict[str, float]]:
    out = _get_model().encode(texts, return_dense=False, return_sparse=True, batch_size=batch_size)
    return [_to_float_dict(w) for w in out["lexical_weights"]]


def encode_both(texts: list[str], batch_size: int = 12) -> tuple[list[list[float]], list[dict[str, float]]]:
    out = _get_model().encode(texts, return_dense=True, return_sparse=True, batch_size=batch_size)
    dense = out["dense_vecs"].tolist()
    sparse = [_to_float_dict(w) for w in out["lexical_weights"]]
    return dense, sparse
