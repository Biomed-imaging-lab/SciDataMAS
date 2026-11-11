"""Stage 4: aggregate results.csv into per-(model, generator) and
per-(standard, model, generator) mean/std recall.

Usage:
    python aggregate_results.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import config


def main():
    df = pd.read_csv(config.RESULTS_CSV)
    ok = df[df["status"] == "ok"].copy()
    ok["recall"] = ok["recall"].astype(float)

    print(f"{len(df)} total cells, {len(ok)} ok, {len(df) - len(ok)} failed generations.\n")

    by_model_gen = ok.groupby(["model", "generator"])["recall"].agg(["mean", "std", "count"])
    print("=== Mean recall by (model, generator) ===")
    print(by_model_gen, "\n")

    by_standard = ok.groupby(["standard_id", "model", "generator"])["recall"].agg(
        ["mean", "std", "count"]
    )
    print("=== Mean recall by (standard, model, generator) ===")
    print(by_standard)

    by_model_gen.to_csv(config.SUMMARY_CSV)
    print(f"\nWrote summary to {config.SUMMARY_CSV}")


if __name__ == "__main__":
    main()
