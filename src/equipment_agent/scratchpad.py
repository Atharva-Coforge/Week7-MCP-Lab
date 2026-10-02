"""One readable markdown file per request."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

SCRATCHPAD_DIR = Path(__file__).resolve().parents[2] / "scratchpads"


def start_scratchpad(employee_id: str) -> Path:
    """Create scratchpads/<timestamp>_<employee_id>.md and return its path."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    SCRATCHPAD_DIR.mkdir(parents=True, exist_ok=True)
    path = SCRATCHPAD_DIR / f"{stamp}_{employee_id}.md"
    path.write_text(f"# Equipment request {employee_id}\n\n", encoding="utf-8")
    return path


def append_block(path: Path, heading: str, body: str) -> None:
    """Append a Thought, Action, Observation, Reflection, or Decision block."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"## {heading}\n\n{body.rstrip()}\n\n")
