"""Run the one-shot checkpoint: get_employee_info for E101, one scratchpad step."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from equipment_agent.agent import run_one_shot  # noqa: E402


if __name__ == "__main__":
    asyncio.run(run_one_shot())
