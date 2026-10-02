from equipment_agent import scratchpad


def test_scratchpad_records_one_step(tmp_path, monkeypatch):
    monkeypatch.setattr(scratchpad, "SCRATCHPAD_DIR", tmp_path)

    path = scratchpad.start_scratchpad("E101")
    scratchpad.append_block(path, "Thought", "Look up the employee first.")
    scratchpad.append_block(path, "Action", 'get_employee_info {"employee_id": "E101"}')
    scratchpad.append_block(path, "Observation", '{"found": true}')

    text = path.read_text(encoding="utf-8")
    assert path.parent == tmp_path
    assert path.name.endswith("_E101.md")
    assert "## Thought" in text
    assert "## Action" in text
    assert "## Observation" in text
    assert "Look up the employee first." in text
