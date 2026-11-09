"""Expose one read-only classroom document through MCP."""

import os

from fastmcp import FastMCP

mcp = FastMCP("Course Filesystem Server")
EVENT_PLAN = os.path.join(os.path.dirname(__file__), "..", "sample_data", "event-plan.md")


@mcp.tool()
def read_event_plan() -> str:
    """Read the published Perth photography walk plan."""
    # Fix the path on the server so callers cannot choose a different file.
    with open(EVENT_PLAN, encoding="utf-8") as file:
        return file.read()


if __name__ == "__main__":
    mcp.run(transport="stdio")
