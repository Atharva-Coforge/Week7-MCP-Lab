"""Plain equipment-request functions. Tests call these directly."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("EQUIPMENT_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))


def get_employee_info(employee_id: str, as_of: date | str | None = None) -> dict:
    """Return the employee record, with equipment age computed as of `as_of`.

    `as_of` defaults to the day of the call. Unit tests pass 2026-10-01.
    An unknown id returns `found: false` and does not invent a record.
    """
    on = datetime.now(UTC).date() if as_of is None else _coerce_date(as_of)
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


def catalog_items() -> list[str]:
    """Item names stored in the policy file. Adding an item there is enough to recognize it."""
    policies = _load_json("policies.json")
    names: set[str] = set()
    for rules in policies.values():
        if isinstance(rules, dict):
            names.update(str(name) for name in rules)
    return sorted(names)


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
    quantity: int = 1,
    adding: bool = False,
    replacing: bool = False,
) -> dict:
    """Return whether `quantity` units of `item` are inside policy on `as_of`.

    `as_of` defaults to the day of the call. `quantity` defaults to one unit.
    `adding` is true when the sentence asks for one more of this item.
    `replacing` leaves the count unchanged and uses the refresh rule.
    A bare request for one more of an item they are already at the cap for,
    and they are allowed more than one, is `at_limit` unless it is a replacement.
    A terminated employee stops the check before item and refresh rules run.
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
    decision = _apply_limit(
        employee_id,
        catalog_item,
        role=role,
        status=employee["status"],
        owned=owned,
        max_count=rule["max_count"],
        refresh_years=rule["refresh_years"],
        quantity=_quantity(quantity),
        adding=adding,
        replacing=replacing,
    )
    return decision


def flag_for_human_review(employee_id: str, request: str, reason: str) -> dict:
    """Append one escalation line and return the saved record."""
    record = {
        "employee_id": employee_id,
        "request": request,
        "reason": reason,
        "escalated_at": datetime.now(UTC).isoformat(),
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
    quantity: int = 1,
    adding: bool = False,
    replacing: bool = False,
) -> dict:
    count = len(owned)
    details = {
        "role": role,
        "status": status,
        "count": count,
        "max_count": max_count,
        "refresh_years": refresh_years,
        "quantity": quantity,
        "adding": adding,
        "replacing": replacing,
    }
    bare_at_cap = not replacing and not adding and quantity == 1 and count == max_count and max_count > 1
    adds_units = (not replacing) and (quantity > 1 or adding or bare_at_cap)
    if adds_units and (quantity > max_count or count + quantity > max_count):
        return _eligibility(employee_id, item, False, "at_limit", **details)
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


def _quantity(value: int) -> int:
    """A missing or non-positive quantity is one unit."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    return max(number, 1)


def _coerce_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _load_json(name: str):
    with (DATA_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)
