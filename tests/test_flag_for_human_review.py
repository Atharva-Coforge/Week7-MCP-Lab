import json

from equipment_agent import tools


def test_appends_one_escalation_line(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "DATA_DIR", tmp_path)

    saved = tools.flag_for_human_review(
        "E103",
        "Can I get new equipment? My setup isn't great.",
        "The request does not name a laptop or a monitor.",
    )

    lines = (tmp_path / "escalations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == saved
    assert saved["employee_id"] == "E103"
    assert saved["request"] == "Can I get new equipment? My setup isn't great."
    assert saved["reason"] == "The request does not name a laptop or a monitor."
    assert saved["escalated_at"]


def test_second_call_appends_another_line(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "DATA_DIR", tmp_path)

    tools.flag_for_human_review("E103", "unclear setup", "no catalog item")
    tools.flag_for_human_review("E104", "damaged laptop", "early replacement")

    lines = (tmp_path / "escalations.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [record["employee_id"] for record in records] == ["E103", "E104"]
