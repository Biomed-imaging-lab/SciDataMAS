"""Prints a projected LLM call range for a probing run (session length is now
open-ended, bounded by [MIN_QUESTIONS, MAX_QUESTIONS], so this is a range +
an assumed-average estimate rather than an exact count). No LLM calls made.

Usage:
    python dry_run.py [target_key ...] [--avg-questions 8]
"""

import sys

import config
from roster import PROBES


def main():
    args = sys.argv[1:]
    avg_questions = (config.MIN_QUESTIONS + config.MAX_QUESTIONS) / 2

    targets = []
    i = 0
    while i < len(args):
        if args[i] == "--avg-questions":
            avg_questions = float(args[i + 1])
            i += 2
        else:
            targets.append(args[i])
            i += 1
    targets = targets or config.DEFAULT_TARGETS

    n_probes = len(PROBES)
    n_sessions = config.K_RUNS * n_probes

    # per question: 1 ask-or-stop call + 1 judge call (judge always runs,
    # since the retriever always returns top-K candidates); each session also
    # pays one extra ask-or-stop call for its final "stop" decision.
    min_llm = n_sessions * (config.MIN_QUESTIONS * 2 + 1)
    max_llm = n_sessions * (config.MAX_QUESTIONS * 2 + 1)
    avg_llm = n_sessions * (avg_questions * 2 + 1)
    avg_emb = n_sessions * avg_questions  # question embeddings, excl. one-time field-embedding pass per target

    print(f"Probes: {[p.id for p in PROBES]}")
    print(f"k_runs={config.K_RUNS}, sessions_per_target={n_sessions}")
    print(f"MIN_QUESTIONS={config.MIN_QUESTIONS}, MAX_QUESTIONS={config.MAX_QUESTIONS}, assumed avg={avg_questions}\n")

    total_avg_llm = 0
    total_avg_emb = 0
    for target_key in targets:
        print(
            f"  {target_key}: {min_llm:.0f}-{max_llm:.0f} LLM calls "
            f"(avg~{avg_llm:.0f} at {avg_questions} questions/session), "
            f"~{avg_emb:.0f} question-embedding calls + 1 field-embedding pass"
        )
        total_avg_llm += avg_llm
        total_avg_emb += avg_emb

    print(f"\nTotal across {len(targets)} target(s) at assumed average: ~{total_avg_llm:.0f} LLM calls, ~{total_avg_emb:.0f} embedding calls")


if __name__ == "__main__":
    main()
