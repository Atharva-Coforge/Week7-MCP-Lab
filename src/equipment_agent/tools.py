"""Plain equipment-request functions. Tests call these directly."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
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


def get_policy_limits(role: str) -> dict:
    """Return the item rules for a role, or an error when the role is unknown."""
    policies = _load_json("policies.json")
    if role not in policies:
        return {"role": role, "error": "unknown_role"}
    return {"role": role, "limits": policies[role]}


def check_request_eligibility(
    employee_id: str,
    item: str,
    as_of: date | str | None = None,
) -> dict:
    """Return whether `item` is inside policy for this employee on `as_of`.

    `as_of` defaults to the day of the call. A terminated employee stops the
    check before item and refresh rules run.
    """
    catalog_item = item.strip().lower()
    employee = get_employee_info(employee_id, as_of=as_of)
    if not employee["found"]:
        return _eligibility(employee_id, catalog_item, False, "unknown_employee")
    if employee["status"] != "active":
        return _eligibility(
            employee_id,
            catalog_item,
            False,
            "terminated",
            role=employee["role"],
            status=employee["status"],
        )

    role = employee["role"]
    policies = _load_json("policies.json")
    if role not in policies:
        return _eligibility(
            employee_id,
            catalog_item,
            False,
            "unknown_role",
            role=role,
            status=employee["status"],
        )
    rules = policies[role]
    if catalog_item not in rules:
        return _eligibility(
            employee_id,
            catalog_item,
            False,
            "unknown_item",
            role=role,
            status=employee["status"],
        )

    rule = rules[catalog_item]
    owned = [asset for asset in employee["equipment"] if asset["item"] == catalog_item]
    return _apply_limit(
        employee_id,
        catalog_item,
        role=role,
        status=employee["status"],
        owned=owned,
        max_count=rule["max_count"],
        refresh_years=rule["refresh_years"],
    )


def flag_for_human_review(employee_id: str, request: str, reason: str) -> dict:
    """Append one escalation line and return the saved record."""
    record = {
        "employee_id": employee_id,
        "request": request,
        "reason": reason,
        "escalated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = DATA_DIR / "escalations.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def _apply_limit(
    employee_id: str,
    item: str,
    *,
    role: str,
    status: str,
    owned: list[dict],
    max_count: int,
    refresh_years: int | None,
) -> dict:
    count = len(owned)
    details = {
        "role": role,
        "status": status,
        "count": count,
        "max_count": max_count,
        "refresh_years": refresh_years,
    }
    if count == 0:
        if max_count < 1:
            return _eligibility(employee_id, item, False, "at_limit", **details)
        return _eligibility(employee_id, item, True, "within_policy", **details)
    if count > max_count:
        return _eligibility(employee_id, item, False, "at_limit", **details)

    newest = max(owned, key=lambda asset: asset["assigned_on"])
    age_years = newest["age_years"]
    details["age_years"] = age_years
    if refresh_years is None or age_years < refresh_years:
        return _eligibility(employee_id, item, False, "too_soon", **details)
    return _eligibility(employee_id, item, True, "within_policy", **details)


def _eligibility(
    employee_id: str,
    item: str,
    eligible: bool,
    reason: str,
    **details: object,
) -> dict:
    return {
        "employee_id": employee_id,
        "item": item,
        "eligible": eligible,
        "reason": reason,
        **details,
    }


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
