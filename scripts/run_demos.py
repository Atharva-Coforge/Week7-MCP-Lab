"""Ask the ReAct agent to decide one equipment request."""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from equipment_agent.agent import run_request  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Decide one equipment request with the ReAct agent.")
    parser.add_argument("--employee-id", required=True, help="Employee id, for example E101")
    parser.add_argument("--request", required=True, help="The employee's sentence")
    args = parser.parse_args()
    asyncio.run(run_request(args.employee_id, args.request))


if __name__ == "__main__":
    main()
