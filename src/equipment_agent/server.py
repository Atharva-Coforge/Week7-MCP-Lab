"""MCP server. Registers plain functions and adds no business logic of its own."""

from mcp.server.mcpserver import MCPServer

from equipment_agent.tools import check_request_eligibility as decide_eligibility
from equipment_agent.tools import flag_for_human_review as record_escalation
from equipment_agent.tools import get_employee_info as lookup_employee
from equipment_agent.tools import get_policy_limits as lookup_policy

server = MCPServer("equipment-agent")


@server.tool()
def get_employee_info(employee_id: str, as_of: str | None = None) -> dict:
    """Look up an employee's role, status, tenure, and current equipment.

    Age is computed from each asset's assigned_on date. Pass as_of as
    YYYY-MM-DD. When as_of is omitted, age is computed for the day of the call.
    """
    return lookup_employee(employee_id, as_of=as_of)


@server.tool()
def get_policy_limits(role: str) -> dict:
    """Return what a role may receive, and how often."""
    return lookup_policy(role)


@server.tool()
def check_request_eligibility(
    employee_id: str,
    item: str,
    as_of: str | None = None,
    quantity: int = 1,
    adding: bool = False,
    replacing: bool = False,
) -> dict:
    """Return whether an employee may receive `quantity` units of an item.

    Pass as_of as YYYY-MM-DD. When as_of is omitted, the check uses the day of the call.
    `quantity` is how many units the sentence asks for. It defaults to 1.
    `adding` is true when the sentence asks for one more of this item.
    `replacing` leaves the count unchanged. A bare request at the cap is not eligible
    unless it is a replacement.
    """
    return decide_eligibility(
        employee_id,
        item,
        as_of=as_of,
        quantity=quantity,
        adding=adding,
        replacing=replacing,
    )


@server.tool()
def flag_for_human_review(employee_id: str, request: str, reason: str) -> dict:
    """Record an escalation for a human reviewer and return the saved line."""
    return record_escalation(employee_id, request, reason)
