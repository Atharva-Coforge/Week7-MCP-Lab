import json
from datetime import date

from equipment_agent import tools

AS_OF = date(2026, 10, 1)


def test_known_employee_includes_computed_age():
    result = tools.get_employee_info("E101", as_of=AS_OF)

    assert result["found"] is True
    assert result["role"] == "standard"
    assert result["status"] == "active"
    assert result["tenure_years"] == 5
    monitor = next(item for item in result["equipment"] if item["asset_tag"] == "MON-E101-1")
    laptop = next(item for item in result["equipment"] if item["asset_tag"] == "LPT-E101-1")
    assert monitor["assigned_on"] == "2022-04-21"
    assert monitor["age_years"] == 4
    assert laptop["age_years"] == 2


def test_age_before_anniversary_is_not_a_full_year():
    result = tools.get_employee_info("E102", as_of=AS_OF)

    laptop = next(item for item in result["equipment"] if item["item"] == "laptop")
    assert laptop["assigned_on"] == "2025-12-01"
    assert laptop["age_years"] == 0


def test_terminated_status_is_returned():
    result = tools.get_employee_info("E107", as_of=AS_OF)

    assert result["found"] is True
    assert result["status"] == "terminated"
    assert result["role"] == "standard"


def test_missing_employee_id():
    assert tools.get_employee_info("E999", as_of=AS_OF) == {
        "found": False,
        "employee_id": "E999",
    }


def test_reads_the_patched_data_directory(tmp_path, monkeypatch):
    record = {
        "employee_id": "E900",
        "name": "Pat Example",
        "role": "contractor",
        "status": "active",
        "tenure_years": 3,
        "equipment": [
            {"asset_tag": "LPT-E900-1", "item": "laptop", "assigned_on": "2022-10-01"}
        ],
    }
    (tmp_path / "employees.json").write_text(json.dumps([record]))
    monkeypatch.setattr(tools, "DATA_DIR", tmp_path)

    found = tools.get_employee_info("E900", as_of=AS_OF)
    missing = tools.get_employee_info("E101", as_of=AS_OF)

    assert found["found"] is True
    assert found["role"] == "contractor"
    assert found["equipment"][0]["age_years"] == 4
    assert missing == {"found": False, "employee_id": "E101"}
