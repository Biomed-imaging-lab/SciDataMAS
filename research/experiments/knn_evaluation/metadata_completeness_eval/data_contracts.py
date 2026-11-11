"""QuestionRecord data contract + JSONL persistence.

Every probing question is persisted as one JSONL row, including the raw
retriever similarity score for every metadata field (`field_scores`) — this is
what lets the Aggregator re-split absent vs. present_but_insufficient at any
NEED_COMP_THRES value later, without re-running any LLM or embedding call.

Each (run_id, probe_id) is now an open-ended session (see agents/probe.py):
question count varies per session, bounded by [MIN_QUESTIONS, MAX_QUESTIONS].
Because session length isn't fixed, resumability can't just diff against a
question count — sessions.json separately marks which (run_id, probe_id)
sessions ran to completion, so an interrupted run resumes only the
unfinished/unstarted sessions rather than guessing from record counts.
"""

import json
from pathlib import Path
from typing import Dict, List, Literal

from pydantic import BaseModel


class QuestionRecord(BaseModel):
    run_id: int
    session_q_idx: int  # position within this (run_id, probe_id) session
    probe_id: str
    probe_mode: Literal["mainstream", "adversarial"]
    question: str
    question_valid: bool

    field_scores: Dict[str, float]
    candidate_fields: List[str]
    sufficient: bool
    good_fields: List[str]
    reason: str

    target_key: str
    model_probe: str
    embedding_model: str


class SessionMeta(BaseModel):
    run_id: int
    probe_id: str
    n_questions: int
    stop_reason: Literal["probe_decided", "max_reached"]


def append_record(path: Path, record: QuestionRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fio:
        fio.write(record.model_dump_json() + "\n")


def load_records(path: Path) -> List[QuestionRecord]:
    if not path.exists():
        return []
    records = []
    with open(path, "rt") as fio:
        for line in fio:
            line = line.strip()
            if not line:
                continue
            records.append(QuestionRecord(**json.loads(line)))
    return records


def _sessions_path(records_path: Path) -> Path:
    return records_path.with_suffix(".sessions.json")


def load_sessions_meta(records_path: Path) -> Dict[str, SessionMeta]:
    path = _sessions_path(records_path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {k: SessionMeta(**v) for k, v in data.items()}


def save_session_meta(records_path: Path, meta: SessionMeta) -> None:
    path = _sessions_path(records_path)
    sessions = load_sessions_meta(records_path)
    key = f"{meta.run_id}:{meta.probe_id}"
    sessions[key] = meta
    path.write_text(json.dumps({k: v.model_dump() for k, v in sessions.items()}, indent=2))


def session_done(records_path: Path, run_id: int, probe_id: str) -> bool:
    sessions = load_sessions_meta(records_path)
    return f"{run_id}:{probe_id}" in sessions


def load_records_for_session(records_path: Path, run_id: int, probe_id: str) -> List[QuestionRecord]:
    return [
        r for r in load_records(records_path) if r.run_id == run_id and r.probe_id == probe_id
    ]
