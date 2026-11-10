"""Expose one read-only classroom document through MCP."""

from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("Course Filesystem Server")
EVENT_PLAN = Path(__file__).resolve().parents[1] / "sample_data" / "event-plan.md"


@mcp.tool()
def read_event_plan() -> str:
    """Read the classroom orientation plan, including venues and the wet-weather rule."""
    # Fix the path on the server so callers cannot choose a different file.
    with open(EVENT_PLAN, encoding="utf-8") as file:
        return file.read()


if __name__ == "__main__":
    mcp.run(transport="stdio")
