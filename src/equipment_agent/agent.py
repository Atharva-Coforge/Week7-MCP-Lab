"""MCP client for the equipment agent.

`run_one_shot` is the assignment checkpoint: one hardcoded tool call.
`run_request` is the ReAct loop. Demos and CLI questions go through it.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from ollama import AsyncClient, Message, ResponseError

from equipment_agent.logging_setup import get_logger
from equipment_agent.reflection import decision_from_eligibility, reflect_on_draft
from equipment_agent.scratchpad import append_block, start_scratchpad

ROOT = Path(__file__).resolve().parents[2]
ONE_SHOT_EMPLOYEE_ID = "E101"
ONE_SHOT_THOUGHT = (
    "I need this employee's role, status, and current equipment before any policy decision."
)
MAX_STEPS = 8
DECISIONS = ("approved", "denied", "escalated")

_ACTION_LINE = re.compile(r"^Action:\s*([A-Za-z0-9_]+)(?:\s+(\{.*\}))?\s*$", re.MULTILINE)
_ACTION_INPUT_LINE = re.compile(r"^Action Input:\s*(\{.*\})\s*$", re.MULTILINE)
_DECISION_LINE = re.compile(r"^Decision:\s*(approved|denied|escalated)\b", re.IGNORECASE | re.MULTILINE)
_THOUGHT_LINE = re.compile(r"^Thought:\s*(.+)$", re.MULTILINE)


def system_prompt(as_of: str) -> str:
    return f"""You decide equipment requests for the employee id in the user message.
The decision date is {as_of}. That is today for this request. Tools compute equipment age on that date.
Role, status, tenure, and equipment come from tools. Do not trust those facts in the sentence.

Catalog items are laptop, monitor, keyboard, webcam, and phone.
- approved: the sentence names one catalog item, and check_request_eligibility returns eligible true with reason within_policy. count below max_count means the limit is not reached. Do not call flag_for_human_review.
- denied: an ordinary request whose eligibility reason is too_soon or at_limit, or the employee status is terminated. Do not call flag_for_human_review.
- escalated: the sentence names no catalog item, or it asks for an exception such as damage, loss, theft, or an early replacement. Call flag_for_human_review before this decision.

When you call a tool, put one sentence in the message and start it with "Thought:".
When you are finished, do not call a tool. Reply in this form:
Decision: approved
or Decision: denied
or Decision: escalated
Then one short explanation that uses only facts the tools returned.

If you do not make a native tool call, write exactly:
Thought: <one sentence>
Action: <tool_name>
Action Input: <json object>
"""


def decision_date() -> str:
    """The calendar day this request is decided. One request keeps one date."""
    return datetime.now(UTC).date().isoformat()


async def run_one_shot() -> Path:
    """Call get_employee_info for E101 and write one scratchpad step."""
    log = get_logger()
    path = start_scratchpad(ONE_SHOT_EMPLOYEE_ID)
    arguments = {"employee_id": ONE_SHOT_EMPLOYEE_ID, "as_of": decision_date()}
    action = "get_employee_info " + json.dumps(arguments)

    append_block(path, "Thought", ONE_SHOT_THOUGHT)
    append_block(path, "Action", action)

    async with Client(_server_params()) as client:
        result = await client.call_tool("get_employee_info", arguments)

    observation = _tool_result_text(result)
    append_block(path, "Observation", observation)
    log.info("one-shot employee_id=%s tool=get_employee_info scratchpad=%s", ONE_SHOT_EMPLOYEE_ID, path)
    print(path)
    return path


async def run_request(employee_id: str, sentence: str, *, model: str | None = None) -> Path:
    """Run the ReAct loop for one employee sentence and return the scratchpad path."""
    model_name = model or os.environ.get("OLLAMA_MODEL", "qwen3:8b")
    as_of = decision_date()
    log = get_logger()
    log.info("react start employee_id=%s as_of=%s", employee_id, as_of)
    path = start_scratchpad(employee_id)
    append_block(path, "Request", f"employee_id: {employee_id}\nas_of: {as_of}\n\n{sentence}")
    messages: list[dict[str, Any] | Message] = [
        {"role": "system", "content": system_prompt(as_of)},
        {"role": "user", "content": f"employee_id: {employee_id}\nrequest: {sentence}"},
    ]
    called_flag = False
    decision: str | None = None
    seen: dict[str, str] = {}
    stalls = 0
    stop_reason: str | None = None
    rewritten = False

    try:
        async with Client(_server_params()) as mcp:
            listed = await mcp.list_tools()
            tools = mcp_tools_to_ollama(listed.tools)
            ollama = AsyncClient()
            for step in range(1, MAX_STEPS + 1):
                response = await ollama.chat(
                    model=model_name,
                    messages=messages,
                    tools=tools,
                    think=False,
                    stream=False,
                    options={"temperature": 0},
                )
                content = response.message.content or ""
                calls = tool_calls_from_message(response.message, content)
                if calls:
                    if response.message.tool_calls:
                        messages.append(response.message)
                    else:
                        messages.append(
                            {
                                "role": "assistant",
                                "content": content,
                                "tool_calls": [
                                    {"function": {"name": name, "arguments": args}} for name, args in calls
                                ],
                            }
                        )
                    thought = extract_thought(content) or "I need a tool result before deciding."
                    fresh = False
                    for name, args in calls:
                        if name == "flag_for_human_review" and parse_decision(content) == "denied":
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_name": name,
                                    "content": "Not called. A denial does not escalate.",
                                }
                            )
                            continue
                        prepared = prepare_arguments(name, args, employee_id, sentence, as_of)
                        key = action_key(name, prepared)
                        if key in seen:
                            stalls += 1
                            log.info("react step=%s repeated tool=%s", step, name)
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_name": name,
                                    "content": (
                                        seen[key]
                                        + "\nAlready observed. Reply with Decision: approved, denied, or escalated."
                                    ),
                                }
                            )
                            continue
                        observation = await _record_call(
                            mcp, path, log, employee_id, sentence, as_of, step, thought, name, prepared
                        )
                        seen[key] = observation
                        fresh = True
                        stalls = 0
                        if name == "flag_for_human_review":
                            called_flag = True
                        messages.append({"role": "tool", "tool_name": name, "content": observation})
                    if not fresh and stalls >= 1:
                        stop_reason = "The agent repeated a tool call instead of deciding."
                        break
                    continue

                decision = parse_decision(content)
                if decision == "escalated" and not called_flag:
                    await _record_call(
                        mcp,
                        path,
                        log,
                        employee_id,
                        sentence,
                        as_of,
                        step,
                        "The decision is escalated, so I am recording it for a human reviewer.",
                        "flag_for_human_review",
                        {"reason": escalation_reason(content)},
                    )
                    called_flag = True
                if decision:
                    check = reflect_on_draft(decision, latest_eligibility(seen))
                    append_block(path, "Reflection", check["note"])
                    log.info("react reflection confirmed=%s", check["confirmed"])
                    if not check["confirmed"] and not rewritten:
                        rewritten = True
                        messages.append(response.message)
                        messages.append(
                            {
                                "role": "user",
                                "content": check["note"] + " Reply with a Decision that matches that tool result.",
                            }
                        )
                        continue
                    if not check["confirmed"]:
                        decision = decision_from_eligibility(latest_eligibility(seen))
                        content = f"Decision: {decision}\n{check['note']}"
                    append_block(path, "Decision", content.strip())
                    log.info("react decision=%s employee_id=%s scratchpad=%s", decision, employee_id, path)
                    break
                stalls += 1
                if stalls >= 2:
                    stop_reason = "The agent did not call a tool or decide."
                    break
                messages.append(response.message)
                messages.append(
                    {
                        "role": "user",
                        "content": "Call a tool, or finish with Decision: approved, denied, or escalated.",
                    }
                )
            else:
                stop_reason = "The agent stopped after 8 steps without a decision."

            if decision is None:
                decision = "escalated"
                reason = stop_reason or "The agent stopped after 8 steps without a decision."
                if not called_flag:
                    await _record_call(
                        mcp,
                        path,
                        log,
                        employee_id,
                        sentence,
                        as_of,
                        MAX_STEPS,
                        "The loop is stopping, so I am escalating instead of guessing.",
                        "flag_for_human_review",
                        {"reason": reason},
                    )
                final = f"Decision: escalated\n{reason}"
                append_block(path, "Decision", final)
                log.info("react decision=escalated employee_id=%s scratchpad=%s", employee_id, path)
    except httpx.ConnectError as exc:
        raise SystemExit(
            "Ollama is not reachable at http://127.0.0.1:11434. Start it with `ollama serve`."
        ) from exc
    except ResponseError as exc:
        raise SystemExit(f"Ollama request failed: {exc}") from exc

    print(f"Decision: {decision}")
    print(path)
    return path


def parse_text_action(content: str) -> tuple[str, dict] | None:
    """Read one `Action: tool_name` line when the model skips a native tool call."""
    text = _strip_fences(content)
    match = _ACTION_LINE.search(text)
    if not match:
        return None
    name = match.group(1)
    raw = match.group(2)
    if raw is None:
        input_match = _ACTION_INPUT_LINE.search(text)
        raw = input_match.group(1) if input_match else None
    if not raw:
        return name, {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return name, {}
    return name, loaded if isinstance(loaded, dict) else {}


def parse_decision(content: str) -> str | None:
    match = _DECISION_LINE.search(content)
    if not match:
        return None
    return match.group(1).lower()


def extract_thought(content: str) -> str:
    match = _THOUGHT_LINE.search(content)
    if match:
        return match.group(1).strip()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Action") or stripped.lower().startswith("decision:"):
            continue
        return stripped
    return ""


def escalation_reason(content: str) -> str:
    lines: list[str] = []
    seen = False
    for line in content.splitlines():
        if _DECISION_LINE.match(line.strip()):
            seen = True
            continue
        if seen and line.strip():
            lines.append(line.strip())
    return " ".join(lines) or "Escalated for human review."


def latest_eligibility(observations: dict[str, str]) -> dict | None:
    """The last check_request_eligibility payload recorded for this request."""
    found = None
    for text in observations.values():
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "eligible" in data and "reason" in data:
            found = data
    return found


def action_key(name: str, arguments: dict) -> str:
    """Stable identity of a tool call, so a repeat can stop the loop."""
    return f"{name} {json.dumps(arguments, sort_keys=True)}"


def prepare_arguments(
    name: str,
    arguments: dict,
    employee_id: str,
    sentence: str,
    as_of: str,
) -> dict:
    args = dict(arguments)
    if name in {"get_employee_info", "check_request_eligibility"}:
        args.setdefault("employee_id", employee_id)
        args["as_of"] = as_of
    if name == "flag_for_human_review":
        args.setdefault("employee_id", employee_id)
        args.setdefault("request", sentence)
    return args


def mcp_tools_to_ollama(tools: list) -> list[dict]:
    converted = []
    for tool in tools:
        data = tool.model_dump(by_alias=True) if hasattr(tool, "model_dump") else dict(tool)
        schema = data.get("inputSchema") or data.get("input_schema") or {"type": "object", "properties": {}}
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": data.get("name") or tool.name,
                    "description": data.get("description") or "",
                    "parameters": schema,
                },
            }
        )
    return converted


def tool_calls_from_message(message: object, content: str) -> list[tuple[str, dict]]:
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        function = call.function
        calls.append((function.name, _coerce_args(function.arguments)))
    if calls:
        return calls
    parsed = parse_text_action(content)
    return [parsed] if parsed else []


async def _record_call(mcp, path, log, employee_id, sentence, as_of, step, thought, name, args) -> str:
    prepared = prepare_arguments(name, args, employee_id, sentence, as_of)
    action = f"{name} {json.dumps(prepared, sort_keys=True)}"
    append_block(path, "Thought", thought)
    append_block(path, "Action", action)
    result = await mcp.call_tool(name, prepared)
    observation = _tool_result_text(result)
    append_block(path, "Observation", observation)
    log.info("react step=%s %s", step, _call_summary(name, observation))
    return observation


def _call_summary(name: str, observation: str) -> str:
    try:
        data = json.loads(observation)
    except json.JSONDecodeError:
        return f"tool={name}"
    if "reason" in data:
        return f"tool={name} eligible={data.get('eligible')} reason={data.get('reason')}"
    if "found" in data:
        return f"tool={name} found={data.get('found')} role={data.get('role')}"
    if "error" in data:
        return f"tool={name} error={data.get('error')}"
    if name == "flag_for_human_review":
        return f"tool={name} employee_id={data.get('employee_id')}"
    return f"tool={name}"


def _coerce_args(raw: object) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _strip_fences(content: str) -> str:
    return re.sub(r"```(?:json)?", "", content)


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "scripts" / "run_server.py")],
        cwd=ROOT,
    )


def _tool_result_text(result: object) -> str:
    body = result.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined]
    structured = body.get("structuredContent")
    if structured is not None:
        return json.dumps(structured, indent=2)
    chunks = [block["text"] for block in body.get("content") or [] if block.get("text")]
    text = "\n".join(chunks)
    try:
        return json.dumps(json.loads(text), indent=2)
    except json.JSONDecodeError:
        return text
