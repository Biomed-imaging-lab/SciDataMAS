from sklearn.metrics import roc_auc_score
from dataclasses import dataclass
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Tuple


@dataclass
class SimilarityStats:
    """Within-block and cross-block cosine similarity statistics."""

    within_block_mean: float
    within_block_std: float
    cross_block_mean: float
    cross_block_std: float
    separation: float  # within_mean - cross_mean (higher = better clustering)
    n_fields: int
    n_blocks: int


def within_cross_similarities(
    embeddings: np.ndarray,
    block_labels: List[int],
) -> Tuple[np.ndarray, np.ndarray]:
    sim = cosine_similarity(embeddings)

    within, cross = [], []
    n = len(block_labels)
    for i in range(n):
        for j in range(i + 1, n):
            s = float(sim[i, j])
            if block_labels[i] == block_labels[j]:
                within.append(s)
            else:
                cross.append(s)
    return np.array(within), np.array(cross)


def compute_similarity_stats(
    embeddings: np.ndarray,
    block_labels: List[int],
) -> SimilarityStats:
    n = embeddings.shape[0]
    within_sims, cross_sims = within_cross_similarities(embeddings, block_labels)

    wm = float(np.mean(within_sims))
    ws = float(np.std(within_sims))
    cm = float(np.mean(cross_sims))
    cs = float(np.std(cross_sims))

    return SimilarityStats(
        within_block_mean=wm,
        within_block_std=ws,
        cross_block_mean=cm,
        cross_block_std=cs,
        separation=wm - cm,
        n_fields=n,
        n_blocks=len(block_labels),
    )


def compute_auc_separation(
    embeddings: np.ndarray,
    block_labels: List[int],
) -> float:
    sim = cosine_similarity(embeddings)
    similarities = []
    labels = []

    n = len(block_labels)
    for i in range(n):
        for j in range(i + 1, n):
            similarities.append(float(sim[i, j]))
            labels.append(1 if block_labels[i] == block_labels[j] else 0)

    return roc_auc_score(labels, similarities)
