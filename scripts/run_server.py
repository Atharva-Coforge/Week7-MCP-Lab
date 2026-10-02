"""Start the equipment MCP server on stdio."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from equipment_agent.server import server  # noqa: E402


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
