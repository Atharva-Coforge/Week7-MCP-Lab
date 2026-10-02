import json
from datetime import date

from equipment_agent import tools

AS_OF = date(2026, 10, 1)


def test_second_monitor_is_within_policy():
    result = tools.check_request_eligibility("E101", "monitor", as_of=AS_OF)

    assert result["eligible"] is True
    assert result["reason"] == "within_policy"
    assert result["age_years"] == 4
    assert result["count"] == 1
    assert result["max_count"] == 2


def test_manager_laptop_is_too_soon():
    result = tools.check_request_eligibility("E102", "laptop", as_of=AS_OF)

    assert result["eligible"] is False
    assert result["reason"] == "too_soon"
    assert result["age_years"] == 0
    assert result["refresh_years"] == 2


def test_contractor_laptop_on_the_anniversary_is_eligible():
    result = tools.check_request_eligibility("E105", "laptop", as_of=AS_OF)

    assert result["eligible"] is True
    assert result["reason"] == "within_policy"
    assert result["age_years"] == 4


def test_contractor_monitor_is_at_the_limit():
    result = tools.check_request_eligibility("E105", "monitor", as_of=AS_OF)

    assert result["eligible"] is False
    assert result["reason"] == "at_limit"
    assert result["count"] == 0
    assert result["max_count"] == 0
    assert "age_years" not in result


def test_terminated_employee_stops_before_the_refresh_rule():
    result = tools.check_request_eligibility("E107", "laptop", as_of=AS_OF)

    assert result["eligible"] is False
    assert result["reason"] == "terminated"
    assert result["status"] == "terminated"
    assert "age_years" not in result


def test_unknown_employee():
    result = tools.check_request_eligibility("E999", "laptop", as_of=AS_OF)

    assert result["eligible"] is False
    assert result["reason"] == "unknown_employee"


def test_unknown_item():
    result = tools.check_request_eligibility("E101", "phone", as_of=AS_OF)

    assert result["eligible"] is False
    assert result["reason"] == "unknown_item"


def test_unknown_role_and_a_first_laptop(tmp_path, monkeypatch):
    employees = [
        {
            "employee_id": "E900",
            "name": "Pat Example",
            "role": "vendor",
            "status": "active",
            "tenure_years": 1,
            "equipment": [],
        },
        {
            "employee_id": "E901",
            "name": "No Gear",
            "role": "standard",
            "status": "active",
            "tenure_years": 1,
            "equipment": [],
        },
    ]
    policies = {
        "standard": {
            "monitor": {"max_count": 2, "refresh_years": 3},
            "laptop": {"max_count": 1, "refresh_years": 4},
        }
    }
    (tmp_path / "employees.json").write_text(json.dumps(employees))
    (tmp_path / "policies.json").write_text(json.dumps(policies))
    monkeypatch.setattr(tools, "DATA_DIR", tmp_path)

    unknown_role = tools.check_request_eligibility("E900", "laptop", as_of=AS_OF)
    first_laptop = tools.check_request_eligibility("E901", "laptop", as_of=AS_OF)

    assert unknown_role["reason"] == "unknown_role"
    assert unknown_role["eligible"] is False
    assert first_laptop["reason"] == "within_policy"
    assert first_laptop["eligible"] is True
    assert first_laptop["count"] == 0
