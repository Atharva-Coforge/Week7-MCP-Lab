import shutil
from pathlib import Path

import pytest

from equipment_agent import scratchpad
from equipment_agent.agent import parse_decision, run_request
from equipment_agent.llm import ChatReply

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-10-01"
DAMAGED = "I know my laptop is only 1 year old, but it was damaged. Can I get a replacement early?"


def _saw_tool(messages: list[dict], name: str) -> bool:
    return any(message.get("tool_name") == name for message in messages)


class _ApproveAndFlagModel:
    """Tries to approve and flag in one turn. The flag must not be recorded."""

    def __init__(self) -> None:
        self._tried_flag = False

    async def chat(self, messages: list[dict], tools: list) -> ChatReply:
        if not _saw_tool(messages, "check_request_eligibility"):
            return _reply(
                "Thought: I need the eligibility result before I decide.",
                [("check_request_eligibility", {})],
            )
        if not self._tried_flag:
            self._tried_flag = True
            return _reply(
                "Decision: approved\nThis is within policy.",
                [("flag_for_human_review", {"reason": "extra"})],
            )
        return _reply("Decision: approved\nThis is within policy.")


class _StallingModel:
    """Checks eligibility, then never decides. The loop has to finish from the tool result."""

    async def chat(self, messages: list[dict], tools: list) -> ChatReply:
        if not _saw_tool(messages, "check_request_eligibility"):
            return _reply(
                "Thought: I need the eligibility result before I decide.",
                [("check_request_eligibility", {})],
            )
        return _reply("Thought: I am still not sure.")


class _ApprovingModel:
    """Calls eligibility once, then keeps saying approved. Reflection has to correct it."""

    async def chat(self, messages: list[dict], tools: list) -> ChatReply:
        if not _saw_tool(messages, "check_request_eligibility"):
            return _reply(
                "Thought: I need the eligibility result before I decide.",
                [("check_request_eligibility", {})],
            )
        return _reply("Decision: approved\nI approve this request.")


class _UnusedModel:
    """The loop must not ask the model when the employee id is missing."""

    async def chat(self, messages: list[dict], tools: list) -> ChatReply:
        raise AssertionError("the model ran before the missing employee was reported")


def _reply(content: str, calls: list[tuple[str, dict]] | None = None) -> ChatReply:
    calls = calls or []
    message: dict = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = [{"function": {"name": name, "arguments": args}} for name, args in calls]
    return ChatReply(content=content, tool_calls=calls, assistant_message=message)


def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    for name in ("employees.json", "policies.json"):
        shutil.copy(ROOT / "data" / name, data / name)
    monkeypatch.setenv("EQUIPMENT_DATA_DIR", str(data))
    monkeypatch.setattr(scratchpad, "SCRATCHPAD_DIR", tmp_path / "scratchpads")
    monkeypatch.setattr("equipment_agent.agent.decision_date", lambda: AS_OF)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("employee_id", "sentence", "expected", "flagged", "checked"),
    [
        ("E101", "I need a second monitor.", "approved", False, True),
        ("E102", "My laptop is slow, can I get a replacement?", "denied", False, True),
        ("E103", "Can I get new equipment? My setup isn't great.", "escalated", True, False),
        ("E104", DAMAGED, "escalated", True, True),
        ("E101", "I need 200 monitors for gaming", "denied", False, True),
        ("E107", "My laptop is old, can I get a replacement?", "denied", False, True),
    ],
)
async def test_request_decision_and_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    employee_id: str,
    sentence: str,
    expected: str,
    flagged: bool,
    checked: bool,
) -> None:
    _isolate(tmp_path, monkeypatch)

    path = await run_request(employee_id, sentence, llm=_ApprovingModel())
    text = path.read_text(encoding="utf-8")

    assert parse_decision(text) == expected
    assert ("## Action\n\nflag_for_human_review" in text) is flagged
    assert ("## Action\n\ncheck_request_eligibility" in text) is checked
    if sentence.startswith("I need 200"):
        assert '"quantity": 200' in text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("employee_id", "sentence", "expected", "flagged"),
    [
        ("E102", "My laptop is slow, can I get a replacement?", "denied", False),
        ("E104", DAMAGED, "escalated", True),
        ("E103", "Can I get new equipment? My setup isn't great.", "escalated", True),
    ],
)
async def test_a_stall_after_a_check_follows_eligibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    employee_id: str,
    sentence: str,
    expected: str,
    flagged: bool,
) -> None:
    _isolate(tmp_path, monkeypatch)

    path = await run_request(employee_id, sentence, llm=_StallingModel())
    text = path.read_text(encoding="utf-8")

    assert parse_decision(text) == expected
    assert ("## Action\n\nflag_for_human_review" in text) is flagged


@pytest.mark.anyio
async def test_an_approval_does_not_record_a_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate(tmp_path, monkeypatch)

    path = await run_request("E101", "I need a second monitor.", llm=_ApproveAndFlagModel())
    text = path.read_text(encoding="utf-8")

    assert parse_decision(text) == "approved"
    assert "## Action\n\nflag_for_human_review" not in text


@pytest.mark.anyio
async def test_a_missing_employee_is_reported_before_the_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolate(tmp_path, monkeypatch)

    path = await run_request("E105E178430", "hello", llm=_UnusedModel())
    text = path.read_text(encoding="utf-8")

    assert "get_employee_info" in text
    assert "Employee E105E178430 was not found." in text
    assert parse_decision(text) == "denied"
    assert "## Action\n\nflag_for_human_review" not in text
    assert "Model call 1" not in text
