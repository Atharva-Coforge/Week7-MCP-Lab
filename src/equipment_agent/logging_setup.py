"""One logger for the equipment agent. File plus terminal, never stdout."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "equipment_agent.log"
_LOGGER_NAME = "equipment_agent"


def get_logger() -> logging.Logger:
    """Return the shared logger, configuring it on first use."""
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    # stderr keeps MCP stdio intact. stdout is the server's JSON-RPC pipe.
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger
