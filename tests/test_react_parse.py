from equipment_agent.agent import (
    escalation_reason,
    extract_thought,
    parse_decision,
    parse_text_action,
    prepare_arguments,
)


def test_text_action_with_json_on_the_same_line():
    content = 'Thought: Look up the employee.\nAction: get_employee_info {"employee_id": "E101"}'
    assert parse_text_action(content) == ("get_employee_info", {"employee_id": "E101"})


def test_text_action_uses_the_action_input_line():
    content = """Thought: Check the monitor rule.
Action: check_request_eligibility
Action Input: {"employee_id": "E101", "item": "monitor"}
"""
    assert parse_text_action(content) == (
        "check_request_eligibility",
        {"employee_id": "E101", "item": "monitor"},
    )


def test_decision_and_thought_and_escalation_reason():
    content = "Thought: The sentence names no item.\nDecision: escalated\nNo catalog item was named."
    assert parse_decision(content) == "escalated"
    assert extract_thought(content) == "The sentence names no item."
    assert escalation_reason(content) == "No catalog item was named."


def test_denied_decision_is_lowercase():
    assert parse_decision("Decision: DENIED\nThe laptop is inside the refresh window.") == "denied"


def test_prepare_arguments_uses_the_request_date():
    info = prepare_arguments(
        "get_employee_info",
        {"as_of": "2020-01-01"},
        "E101",
        "I need a second monitor.",
        as_of="2026-10-31",
    )
    flag = prepare_arguments(
        "flag_for_human_review",
        {"reason": "damaged"},
        "E104",
        "It was damaged.",
        as_of="2026-10-31",
    )
    assert info["as_of"] == "2026-10-31"
    assert info["employee_id"] == "E101"
    assert flag["request"] == "It was damaged."
    assert flag["reason"] == "damaged"
