"""Run one equipment request, or the four graded demos."""

import argparse
import asyncio
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from equipment_agent.agent import run_request  # noqa: E402

DEMOS = (
    ("E101", "I need a second monitor.", "01_approved_second_monitor.md", "approved"),
    ("E102", "My laptop is slow, can I get a replacement?", "02_denied_laptop_too_new.md", "denied"),
    ("E103", "Can I get new equipment? My setup isn't great.", "03_escalated_unclear_reason.md", "escalated"),
    (
        "E104",
        "I know my laptop is only 1 year old, but it was damaged. Can I get a replacement early?",
        "04_escalated_outside_policy.md",
        "escalated",
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Decide equipment requests with the ReAct agent.")
    parser.add_argument("--all", action="store_true", help="Run the four graded demos into artifacts/demos")
    parser.add_argument("--employee-id", help="Employee id, for example E101")
    parser.add_argument("--request", help="The employee's sentence")
    args = parser.parse_args()
    if args.all:
        asyncio.run(run_all())
        return
    if not args.employee_id or not args.request:
        parser.error("Pass --all, or both --employee-id and --request.")
    asyncio.run(run_request(args.employee_id, args.request))


async def run_all() -> None:
    demo_dir = ROOT / "artifacts" / "demos"
    demo_dir.mkdir(parents=True, exist_ok=True)
    for employee_id, sentence, filename, expected in DEMOS:
        print(f"\n=== {employee_id}: {sentence}")
        path = await run_request(employee_id, sentence)
        actual = _decision(path)
        destination = demo_dir / filename
        shutil.copyfile(path, destination)
        print(f"saved {destination}")
        if actual != expected:
            raise SystemExit(f"{employee_id} decided {actual or 'nothing'}, expected {expected}.")


def _decision(path: Path) -> str:
    matches = re.findall(r"^Decision:\s*(approved|denied|escalated)\b", path.read_text(encoding="utf-8"), re.I | re.M)
    return matches[-1].lower() if matches else ""


if __name__ == "__main__":
    main()
