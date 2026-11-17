"""Stage: aggregate outputs/records/{target_key}.jsonl into
outputs/summary/{target_key}.json.

field_rating, gaps, and present_but_insufficient are all derived from the
same stored `field_scores` map on each record, so NEED_COMP_THRES can be
changed here and re-run without touching the JSONL or making any LLM call.

Usage:
    python aggregate.py [target_key ...]   # defaults to config.DEFAULT_TARGETS
"""

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from langchain_openai import OpenAIEmbeddings

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / "rag_curator" / ".env")
os.environ["LANGSMITH_TRACING"] = "false"

import config
from data_contracts import QuestionRecord, load_records, load_sessions_meta
from logging_utils import get_logger

GAP_CLUSTER_SIM_THRESHOLD = 0.8  # question-text cosine sim to collapse into one gap cluster
BORDERLINE_BAND = 0.03  # +/- around NEED_COMP_THRES treated as "close call" for threshold diagnostics


def has_candidate_above(field_scores: Dict[str, float], thres: float) -> bool:
    return any(s >= thres for s in field_scores.values())


def _embed_with_retry(embedder: OpenAIEmbeddings, text: str) -> List[float]:
    import time

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return embedder.embed_query(text)
        except Exception as exc:
            if attempt == config.MAX_RETRIES:
                raise
            time.sleep(config.RETRY_BACKOFF_SECONDS * attempt)


def cluster_gap_questions(questions: List[str], embedder: OpenAIEmbeddings) -> List[List[str]]:
    """Simple union-find clustering by cosine similarity — no LLM call,
    reusing the same embedding model as the retriever so scores are
    comparable across the run."""
    if not questions:
        return []

    vecs = np.array([_embed_with_retry(embedder, q) for q in questions], dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs = vecs / np.maximum(norms, 1e-9)
    sims = vecs @ vecs.T

    parent = list(range(len(questions)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    n = len(questions)
    for i in range(n):
        for j in range(i + 1, n):
            if sims[i, j] >= GAP_CLUSTER_SIM_THRESHOLD:
                union(i, j)

    clusters = defaultdict(list)
    for i, q in enumerate(questions):
        clusters[find(i)].append(q)
    return list(clusters.values())


def build_field_importance(records: List[QuestionRecord], n_runs: int) -> List[dict]:
    """Two normalized importance signals per field, per the user's spec:
    - score_per_question: good_field credits / total questions asked across
      all K runs — "how often, per question, this field turned out useful."
    - run_coverage: fraction of runs (out of n_runs) in which the field was
      useful at least once to ANY probe — "how consistently this field shows
      up as useful across independent runs," robust to one run asking an
      unusually field-hungry sequence of questions.
    Both are computed over the combined (mainstream + adversarial) pool,
    since a field's usefulness is what's being rated here, not which probe
    mode found it — mode split is still available via field_rating."""
    n_questions = len(records)
    if n_questions == 0:
        return []

    raw_count = Counter()
    runs_with_field = defaultdict(set)
    for r in records:
        for f in r.good_fields:
            raw_count[f] += 1
            runs_with_field[f].add(r.run_id)

    rows = [
        {
            "field": f,
            "raw_count": raw_count[f],
            "score_per_question": raw_count[f] / n_questions,
            "run_coverage": len(runs_with_field[f]) / n_runs if n_runs else 0.0,
        }
        for f in raw_count
    ]
    rows.sort(key=lambda row: (-row["run_coverage"], -row["score_per_question"]))
    return rows


def build_diagnostics(
    records: List[QuestionRecord],
    thres: float,
    noise: Dict[str, float],
    gap_clusters: List[List[str]],
    present_but_insufficient: List[dict],
    field_rating: Dict[str, Counter],
    sessions: List["SessionMeta"] = (),
) -> List[str]:
    """Heuristic, human-readable suggestions for improving the probing
    system itself — surfaced here (rather than requiring a human to eyeball
    the JSONL) so problems with the harness show up alongside the results
    they produced."""
    notes = []
    n = len(records)
    if n == 0:
        return notes

    for probe_id, rate in noise.items():
        if rate > 0.2:
            notes.append(
                f"probe '{probe_id}' has a {rate:.0%} invalid-question rate — "
                f"its task_scenario is likely eliciting off-topic questions; "
                f"consider rewriting it to be more concretely goal-grounded."
            )

    borderline = 0
    for r in records:
        if r.candidate_fields:
            top_score = max(r.field_scores.get(f, 0.0) for f in r.candidate_fields)
            if abs(top_score - thres) <= BORDERLINE_BAND:
                borderline += 1
    if borderline / n > 0.15:
        notes.append(
            f"{borderline}/{n} records have their top candidate score within "
            f"+/-{BORDERLINE_BAND} of NEED_COMP_THRES ({thres}) — the absent vs. "
            f"present_but_insufficient split is sensitive to the exact threshold "
            f"here; consider re-running aggregate_target with a couple of nearby "
            f"thresholds (no LLM calls needed) to check result stability."
        )

    gap_rate = sum(len(c) for c in gap_clusters) / n
    if gap_rate > 0.4:
        notes.append(
            f"{gap_rate:.0%} of questions landed in gaps (nothing retrieved above "
            f"threshold) — cross-check against the noise rates above: if noise is "
            f"also high, probes may be asking off-target questions rather than the "
            f"metadata being genuinely incomplete."
        )

    if sessions:
        n_sessions = len(sessions)
        at_min = sum(1 for s in sessions if s.n_questions <= config.MIN_QUESTIONS)
        at_max = sum(1 for s in sessions if s.stop_reason == "max_reached")
        avg_q = sum(s.n_questions for s in sessions) / n_sessions
        if at_min / n_sessions > 0.3:
            notes.append(
                f"{at_min}/{n_sessions} sessions stopped at exactly MIN_QUESTIONS "
                f"({config.MIN_QUESTIONS}) — possible premature-stopping bias (the "
                f"probe declaring 'done' as soon as it's allowed to, rather than "
                f"when it genuinely has enough); consider raising MIN_QUESTIONS or "
                f"spot-checking a few of these sessions' transcripts."
            )
        if at_max / n_sessions > 0.2:
            notes.append(
                f"{at_max}/{n_sessions} sessions hit MAX_QUESTIONS ({config.MAX_QUESTIONS}) "
                f"without the probe choosing to stop — either genuinely thorough "
                f"probes on a sparse metadata target, or the judge/ask prompts are "
                f"too reluctant to declare sufficiency; consider raising MAX_QUESTIONS "
                f"or spot-checking whether later questions in these sessions are still "
                f"informative or just repeating earlier ones."
            )
        notes.append(f"session length: avg={avg_q:.1f} questions (n_sessions={n_sessions}).")

    all_rated_fields = set(field_rating["mainstream"]) | set(field_rating["adversarial"])
    if all_rated_fields:
        top_field, top_count = max(
            ((f, field_rating["mainstream"].get(f, 0) + field_rating["adversarial"].get(f, 0)) for f in all_rated_fields),
            key=lambda kv: kv[1],
        )
        if top_count / n > 0.5:
            notes.append(
                f"field '{top_field}' alone accounts for {top_count}/{n} good_field "
                f"credits — either a genuinely central field, or several probes are "
                f"converging on the same generic field; worth a manual spot-check."
            )

    return notes


def aggregate_target(target_key: str, thres: Optional[float] = None) -> dict:
    thres = thres if thres is not None else config.NEED_COMP_THRES
    records_path = config.RECORDS_DIR / f"{target_key}.jsonl"
    records = load_records(records_path)
    if not records:
        return {"target_key": target_key, "n_records": 0}

    field_rating = {"mainstream": Counter(), "adversarial": Counter()}
    gap_questions = []
    present_but_insufficient = []
    noise_by_probe = defaultdict(lambda: {"invalid": 0, "total": 0})

    for r in records:
        for f in r.good_fields:
            field_rating[r.probe_mode][f] += 1

        noise_by_probe[r.probe_id]["total"] += 1
        if not r.question_valid:
            noise_by_probe[r.probe_id]["invalid"] += 1

        candidate_above = has_candidate_above(r.field_scores, thres)
        if not r.sufficient:
            if candidate_above:
                present_but_insufficient.append(
                    {
                        "probe_id": r.probe_id,
                        "probe_mode": r.probe_mode,
                        "question": r.question,
                        "reason": r.reason,
                        "top_candidates": sorted(
                            r.field_scores.items(), key=lambda kv: -kv[1]
                        )[: config.MAX_CANDIDATES],
                    }
                )
            else:
                gap_questions.append(r.question)

    embedder = OpenAIEmbeddings(model=config.EMBEDDING_MODEL)
    gap_clusters = cluster_gap_questions(gap_questions, embedder)

    noise = {
        probe_id: (v["invalid"] / v["total"] if v["total"] else 0.0)
        for probe_id, v in noise_by_probe.items()
    }

    sessions = list(load_sessions_meta(records_path).values())
    n_runs = len({r.run_id for r in records})  # actual runs present, not the (possibly overridden) config default
    diagnostics = build_diagnostics(
        records, thres, noise, gap_clusters, present_but_insufficient, field_rating, sessions
    )
    field_importance = build_field_importance(records, n_runs)

    return {
        "target_key": target_key,
        "n_records": len(records),
        "n_runs": n_runs,
        "need_comp_thres_used": thres,
        "field_importance": field_importance,
        "field_rating": {
            "mainstream": dict(field_rating["mainstream"].most_common()),
            "adversarial": dict(field_rating["adversarial"].most_common()),
        },
        "gaps": [
            {"cluster_questions": cluster, "size": len(cluster)} for cluster in gap_clusters
        ],
        "unanswered_questions": gap_questions,
        "present_but_insufficient": present_but_insufficient,
        "noise": noise,
        "diagnostics": diagnostics,
    }


def print_summary(summary: dict, logger) -> None:
    """Console-friendly view of the two things the user wants to watch after
    every K-run experiment: normalized field importance, and the raw list of
    questions nothing relevant was found for."""
    if summary.get("n_records", 0) == 0:
        logger.info(f"{summary['target_key']}: no records yet")
        return

    logger.info(f"\n=== {summary['target_key']} — field importance (normalized over {summary['n_records']} questions, {summary['n_runs']} runs) ===")
    logger.info(f"{'field':<45} {'score/question':>15} {'run_coverage':>13} {'raw':>5}")
    for row in summary["field_importance"]:
        logger.info(
            f"{row['field']:<45} {row['score_per_question']:>15.2f} {row['run_coverage']:>13.2f} {row['raw_count']:>5}"
        )

    logger.info(f"\n=== {summary['target_key']} — unanswered questions ({len(summary['unanswered_questions'])}) ===")
    for q in summary["unanswered_questions"]:
        logger.info(f"  - {q}")


def main():
    targets = sys.argv[1:] or config.DEFAULT_TARGETS
    config.SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    for target_key in targets:
        logger = get_logger(target_key, name="mce.aggregate")
        summary = aggregate_target(target_key)
        out_path = config.SUMMARY_DIR / f"{target_key}.json"
        out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        logger.info(f"{target_key}: wrote {out_path} ({summary.get('n_records', 0)} records)")
        for note in summary.get("diagnostics", []):
            logger.info(f"  [diagnostic] {note}")
        print_summary(summary, logger)


if __name__ == "__main__":
    main()
