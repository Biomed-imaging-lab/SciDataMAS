"""Shared logging setup: every run/aggregate script logs to both the console
and a per-target file under outputs/logs/, so intermediate results (each
question/candidates/verdict, retries, empty-candidate cases) can be inspected
after the fact without rerunning anything.
"""

import logging
import sys
from pathlib import Path

import config


def get_logger(target_key: str, name: str = "mce") -> logging.Logger:
    logs_dir = config.OUTPUTS_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"{name}.{target_key}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:  # avoid duplicate handlers on repeated calls (e.g. tests)
        return logger

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = logging.FileHandler(logs_dir / f"{target_key}.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
