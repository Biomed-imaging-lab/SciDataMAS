"""Stage: run one open-ended probing session per (run_id, probe), writing one
QuestionRecord per question to outputs/records/{target_key}.jsonl and a
completion marker per session to outputs/records/{target_key}.sessions.json.

Resumable at session granularity: a session already marked complete is
skipped entirely; an interrupted session is restarted from scratch (its
partial records are superseded — session-level state, i.e. the moderated
transcript, isn't itself persisted, only the question/verdict outcomes are,
so a clean restart is the simplest correct way to resume rather than trying
to replay a partial transcript).

Logs every question/candidates/verdict at DEBUG (and retries/failures at
WARNING/ERROR) to outputs/logs/{target_key}.log, and a per-target summary at
INFO — see logging_utils.py.

Usage:
    python run_probing.py [target_key ...]   # defaults to config.DEFAULT_TARGETS
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / "rag_curator" / ".env")
os.environ["LANGSMITH_TRACING"] = "false"  # shared .env enables it; this run doesn't need it and it adds latency

import config
from agents.probe import ProbeAgent
from data_contracts import SessionMeta, append_record, save_session_meta, session_done
from logging_utils import get_logger
from retriever import Retriever
from roster import PROBES
from scenario_source import get_provider_for


def run_target(target_key: str, k_runs: int = None) -> None:
    provider = get_provider_for(target_key)
    k_runs = k_runs if k_runs is not None else config.K_RUNS

    logger = get_logger(target_key)
    logger.info(f"{target_key}: loading metadata + scenarios ({provider.__class__.__name__}, k_runs={k_runs})")
    metadata = provider.get_metadata(target_key)
    scenarios = provider.get_scenarios(target_key, k=k_runs)

    records_path = config.RECORDS_DIR / f"{target_key}.jsonl"

    logger.info(f"{target_key}: embedding {len(metadata)} fields")
    retriever = Retriever(metadata)
    probe_agents = {p.id: ProbeAgent(p) for p in PROBES}

    for run_id in range(k_runs):
        scenario_context = scenarios[run_id % len(scenarios)]

        for probe_cfg in PROBES:
            if session_done(records_path, run_id, probe_cfg.id):
                continue

            probe_agent = probe_agents[probe_cfg.id]
            _run_session_with_retries(
                probe_agent, run_id, scenario_context, retriever, target_key, records_path, logger
            )


def _run_session_with_retries(probe_agent, run_id, scenario_context, retriever, target_key, records_path, logger):
    """Buffers the whole session in memory and only persists it (records +
    completion marker) once it finishes without error — a session that raises
    partway through is retried from scratch rather than leaving orphaned
    partial records in the JSONL that a naive resume-by-append would
    duplicate on the next attempt."""
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            buffered_records = []
            session_meta = None
            for item in probe_agent.run_session(run_id, scenario_context, retriever, target_key, logger):
                if isinstance(item, SessionMeta):
                    session_meta = item
                else:
                    buffered_records.append(item)
                    logger.info(
                        f"  run{run_id} {probe_agent.probe.id} q{item.session_q_idx}: "
                        f"sufficient={item.sufficient} good={item.good_fields}"
                    )

            for record in buffered_records:
                append_record(records_path, record)
            save_session_meta(records_path, session_meta)
            sufficient_rate = sum(r.sufficient for r in buffered_records) / max(len(buffered_records), 1)
            logger.info(
                f"{target_key} run{run_id} {probe_agent.probe.id}: session done "
                f"({session_meta.n_questions} questions, stop_reason={session_meta.stop_reason}, "
                f"sufficient_rate={sufficient_rate:.2f})"
            )
            return
        except Exception as exc:
            if attempt == config.MAX_RETRIES:
                logger.error(
                    f"run{run_id} {probe_agent.probe.id}: session failed after {attempt} attempts: {exc}"
                )
                raise
            logger.warning(
                f"run{run_id} {probe_agent.probe.id}: session retry {attempt}/{config.MAX_RETRIES} after: {exc}"
            )
            time.sleep(config.RETRY_BACKOFF_SECONDS * attempt)


def main():
    targets = sys.argv[1:] or config.DEFAULT_TARGETS
    config.RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    for target_key in targets:
        k_runs = config.GENERATION_K_RUNS if target_key in config.GENERATION_TARGETS else config.K_RUNS
        run_target(target_key, k_runs=k_runs)


if __name__ == "__main__":
    main()
