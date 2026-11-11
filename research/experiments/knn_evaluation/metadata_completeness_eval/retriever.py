"""Deterministic cosine-similarity candidate-field retrieval.

No LLM call. Given a probe's question, scores every field in the target's
metadata by embedding cosine similarity and returns the full score map (so
NEED_COMP_THRES can be re-tuned post-hoc, see data_contracts.py) plus a capped,
thresholded candidate list to hand to the probe for judgment.
"""

import time
from typing import Dict, List

import numpy as np
from langchain_openai import OpenAIEmbeddings

import config
from cache import cached_call


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / max(norm, 1e-9)


class Retriever:
    def __init__(self, metadata: Dict[str, "MDField"], embedder: OpenAIEmbeddings = None):
        self.metadata = metadata
        self.embedder = embedder or OpenAIEmbeddings(model=config.EMBEDDING_MODEL)
        self._field_names = list(metadata.keys())
        self._field_embeds = self._embed_fields()

    def _embed_query(self, text: str) -> np.ndarray:
        def _call():
            for attempt in range(1, config.MAX_RETRIES + 1):
                try:
                    return self.embedder.embed_query(text)
                except Exception as exc:
                    if attempt == config.MAX_RETRIES:
                        raise
                    time.sleep(config.RETRY_BACKOFF_SECONDS * attempt)

        vec = cached_call(
            model=config.EMBEDDING_MODEL,
            payload={"text": text},
            fn=_call,
            to_dict=lambda v: {"v": list(v)},
            from_dict=lambda d: d["v"],
        )
        return _normalize(np.array(vec))

    def _embed_fields(self) -> np.ndarray:
        if not self._field_names:
            return np.zeros((0, 1))
        vecs = [self._embed_query(str(self.metadata[name])) for name in self._field_names]
        return np.array(vecs, dtype=np.float32)

    def score(self, question: str) -> Dict[str, float]:
        if not self._field_names:
            return {}
        q_vec = self._embed_query(question)
        sims = self._field_embeds @ q_vec
        return {name: float(s) for name, s in zip(self._field_names, sims)}

    def candidates(self, field_scores: Dict[str, float]) -> List[str]:
        """Always the top MAX_CANDIDATES nearest fields, unconditional on
        NEED_COMP_THRES: question<->field-description cosine similarity is
        noisy enough (calibration on REMBI: true matches ranged ~0.26-0.55,
        with no clean separation from near-misses) that a hard cutoff here
        drops legitimate candidates. NEED_COMP_THRES is instead applied only
        post-hoc in aggregate.py, against the full field_scores map, to split
        absent vs. present_but_insufficient — a purely analytical use where
        threshold noise just shifts a few borderline cases between the two
        buckets rather than silently hiding a field from the probe."""
        ranked = sorted(field_scores, key=lambda name: -field_scores[name])
        return ranked[: config.MAX_CANDIDATES]

    def field_view(self, field_name: str) -> "MDField":
        return self.metadata[field_name]
