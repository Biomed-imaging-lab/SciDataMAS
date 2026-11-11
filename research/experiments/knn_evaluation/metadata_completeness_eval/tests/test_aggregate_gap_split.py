"""Pure-Python fixture test for the absent vs present_but_insufficient split
in aggregate.py — no API calls.

Usage:
    python tests/test_aggregate_gap_split.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aggregate import has_candidate_above
from data_contracts import QuestionRecord

THRES = 0.45


def make_record(**overrides) -> QuestionRecord:
    base = dict(
        run_id=0,
        session_q_idx=0,
        probe_id="reproducing_biologist",
        probe_mode="mainstream",
        question="test question",
        question_valid=True,
        field_scores={},
        candidate_fields=[],
        sufficient=False,
        good_fields=[],
        reason="",
        target_key="test_target",
        model_probe="gpt-4o",
        embedding_model="text-embedding-3-large",
    )
    base.update(overrides)
    return QuestionRecord(**base)


def main():
    # genuinely absent: nothing scores above threshold
    absent_record = make_record(field_scores={"field_a": 0.2, "field_b": 0.3}, sufficient=False)
    assert not has_candidate_above(absent_record.field_scores, THRES), "expected absent (no candidate above thres)"

    # present but insufficient: something scores above threshold, but probe said not sufficient
    insufficient_record = make_record(
        field_scores={"field_a": 0.2, "field_c": 0.6}, candidate_fields=["field_c"], sufficient=False
    )
    assert has_candidate_above(insufficient_record.field_scores, THRES), "expected present_but_insufficient (candidate above thres)"

    # present and sufficient: not a gap or present_but_insufficient at all
    sufficient_record = make_record(
        field_scores={"field_c": 0.7}, candidate_fields=["field_c"], sufficient=True, good_fields=["field_c"]
    )
    assert has_candidate_above(sufficient_record.field_scores, THRES) and sufficient_record.sufficient

    print("test_aggregate_gap_split: PASS")


if __name__ == "__main__":
    main()
