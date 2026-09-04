"""Structured logging setup for the IncuBrix Lead Engine."""

import logging
import sys
from datetime import datetime
from pathlib import Path
import config


def setup_logging(run_mode: str = "normal") -> logging.Logger:
    """
    Configure logging to both stdout and a timestamped log file.

    Returns the root logger.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(config.LOGS_DIR) / f"run_{run_mode}_{timestamp}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # ── Console (INFO+) ───────────────────────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    ))
    root.addHandler(ch)

    # ── File (DEBUG+) ─────────────────────────────────────────────────────────
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialised | mode={run_mode} | file={log_file}")
    return root
