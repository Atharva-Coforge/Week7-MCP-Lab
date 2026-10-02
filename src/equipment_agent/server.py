"""MCP server. Registers plain functions and adds no business logic of its own."""

from mcp.server.mcpserver import MCPServer

from equipment_agent.tools import get_employee_info as lookup_employee

server = MCPServer("equipment-agent")


@server.tool()
def get_employee_info(employee_id: str, as_of: str | None = None) -> dict:
    """Look up an employee's role, status, tenure, and current equipment.

    Age is computed from each asset's assigned_on date. Pass as_of as
    YYYY-MM-DD. When as_of is omitted, age is computed for the day of the call.
    """
    return lookup_employee(employee_id, as_of=as_of)
