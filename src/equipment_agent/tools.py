"""Plain equipment-request functions. Tests call these directly."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def get_employee_info(employee_id: str, as_of: date | str | None = None) -> dict:
    """Return the employee record, with equipment age computed as of `as_of`.

    `as_of` defaults to the day of the call. Tests and demos pass 2026-10-01.
    An unknown id returns `found: false` and does not invent a record.
    """
    on = date.today() if as_of is None else _coerce_date(as_of)
    for employee in _load_json("employees.json"):
        if employee["employee_id"] != employee_id:
            continue
        return {
            "found": True,
            "employee_id": employee["employee_id"],
            "name": employee["name"],
            "role": employee["role"],
            "status": employee["status"],
            "tenure_years": employee["tenure_years"],
            "equipment": [_with_age(asset, on) for asset in employee["equipment"]],
        }
    return {"found": False, "employee_id": employee_id}


def _with_age(asset: dict, as_of: date) -> dict:
    assigned_on = date.fromisoformat(asset["assigned_on"])
    return {
        "asset_tag": asset["asset_tag"],
        "item": asset["item"],
        "assigned_on": asset["assigned_on"],
        "age_years": _full_years(assigned_on, as_of),
    }


def _full_years(assigned_on: date, as_of: date) -> int:
    years = as_of.year - assigned_on.year
    if (as_of.month, as_of.day) < (assigned_on.month, assigned_on.day):
        years -= 1
    return years


def _coerce_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _load_json(name: str):
    with (DATA_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)
