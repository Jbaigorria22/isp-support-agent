"""MCP server exposing FiberLab tools to the agent (stdio transport).

Run:  python -m fiberlab.mcp_server
"""

from mcp.server.fastmcp import FastMCP

from fiberlab import tools

mcp = FastMCP("fiberlab-support")


@mcp.tool()
def verify_customer(customer_id: str, doc_last3: str) -> dict:
    """Verify the customer's identity. Required before any account tool.

    Args:
        customer_id: FiberLab customer ID, e.g. "C1002".
        doc_last3: last 3 digits of the customer's document number.
    Returns a session_token to pass to account tools.
    """
    return tools.verify_customer(customer_id, doc_last3)


@mcp.tool()
def get_area_outages(zone: str) -> dict:
    """List active service outages in a zone (NORTE, CENTRO or SUR)."""
    return tools.get_area_outages(zone)


@mcp.tool()
def get_modem_status(session_token: str) -> dict:
    """Get the verified customer's ONT status and optical signal level."""
    return tools.get_modem_status(session_token)


@mcp.tool()
def get_speed_history(session_token: str, days: int = 7) -> dict:
    """Get speed tests measured at the ONT (wired) for the last N days (max 7)."""
    return tools.get_speed_history(session_token, days)


@mcp.tool()
def restart_modem(session_token: str) -> dict:
    """Remotely restart the verified customer's ONT. Only after the customer agreed."""
    return tools.restart_modem(session_token)


@mcp.tool()
def create_ticket(session_token: str, category: str, priority: str, summary: str, steps_tried: str) -> dict:
    """Escalate to Level 2 support.

    Args:
        category: no_service | slow_internet | wifi | outage | out_of_scope
        priority: low | medium | high
        summary: symptom, diagnostic results and suggested next action.
        steps_tried: what the customer and the agent already tried.
    """
    return tools.create_ticket(session_token, category, priority, summary, steps_tried)


@mcp.tool()
def get_line_health(session_token: str) -> dict:
    """Get the Line Health Score (0-100) of the verified customer's line.

    green = solvable with home checks; red = needs a technician.
    """
    return tools.get_line_health(session_token)


@mcp.tool()
def get_wifi_info(session_token: str) -> dict:
    """Get the WiFi network name and connected devices. Never returns the password."""
    return tools.get_wifi_info(session_token)


@mcp.tool()
def change_wifi_password(session_token: str, new_password: str) -> dict:
    """Change the WiFi password. Disconnects all devices. Only after the customer agreed."""
    return tools.change_wifi_password(session_token, new_password)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
