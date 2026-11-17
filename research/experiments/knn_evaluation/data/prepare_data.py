#!/usr/bin/env python3
"""Decompress the bundled synthetic metadata tables.

The two CSVs are stored gzipped so a clone stays small (about 3.3 MB instead
of 87 MB). The experiment code reads plain ``.csv`` paths, so run this once
after cloning:

    python prepare_data.py

Existing ``.csv`` files are left untouched.
"""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    found = False
    for gz in sorted(HERE.glob("*.csv.gz")):
        found = True
        out = gz.with_suffix("")  # m1_synth_bio_mds.csv.gz -> m1_synth_bio_mds.csv
        if out.exists():
            print(f"skip  {out.name} (already exists)")
            continue
        with gzip.open(gz, "rb") as src, out.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        print(f"wrote {out.name} ({out.stat().st_size / 1e6:.1f} MB)")
    if not found:
        print("no .csv.gz files found")


if __name__ == "__main__":
    main()
