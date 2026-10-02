"""Connect to the MCP server over stdio and call get_employee_info once."""

import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "scripts" / "run_server.py")],
        cwd=ROOT,
    )
    async with Client(params) as client:
        listed = await client.list_tools()
        print("Registered tools:")
        for tool in listed.tools:
            print(f"- {tool.name}")

        result = await client.call_tool(
            "get_employee_info",
            {"employee_id": "E101", "as_of": "2026-10-01"},
        )
        print()
        print("get_employee_info employee_id=E101 as_of=2026-10-01")
        body = result.model_dump(mode="json", by_alias=True)
        structured = body.get("structuredContent")
        if structured is not None:
            print(json.dumps(structured, indent=2))
        else:
            for block in body.get("content") or []:
                text = block.get("text")
                if text:
                    print(text)
        print(f"isError: {body.get('isError')}")


if __name__ == "__main__":
    asyncio.run(main())
