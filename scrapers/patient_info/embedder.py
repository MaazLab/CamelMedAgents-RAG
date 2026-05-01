from __future__ import annotations
from typing import TYPE_CHECKING

import numpy as np
from sentence_transformers import SentenceTransformer

from scrapers.patient_info.config import EMBEDDING_MODEL, EMBEDDING_DIM, EMBEDDING_BATCH_SIZE
from scrapers.patient_info.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger("embedder")


class Embedder:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or EMBEDDING_MODEL
        logger.info("Loading sentence-transformer model '%s'...", self.model_name)
        self._model = SentenceTransformer(self.model_name)
        self.dimension = self._model.get_sentence_embedding_dimension()
        device = self._model.device
        logger.info(
            "Embedder ready: model=%s, dim=%d, device=%s",
            self.model_name, self.dimension, device,
        )
        if self.dimension != EMBEDDING_DIM:
            logger.warning(
                "Model dimension (%d) differs from configured EMBEDDING_DIM (%d). "
                "Update config.py to match.",
                self.dimension, EMBEDDING_DIM,
            )

    def encode(self, texts: list[str], batch_size: int | None = None) -> np.ndarray:
        bs = batch_size or EMBEDDING_BATCH_SIZE
        embeddings = self._model.encode(
            texts,
            batch_size=bs,
            show_progress_bar=len(texts) > bs,
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]
