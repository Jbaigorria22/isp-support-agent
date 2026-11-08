"""Connects the agent to the FiberLab MCP server (MCP client side).

The graph calls tools through here, over the real MCP protocol (stdio).
"""

import json
import os
import sys
from contextlib import asynccontextmanager

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools


def _parse(result) -> dict:
    """MCP tool results arrive as text or content blocks; normalize to a dict."""
    if isinstance(result, tuple):  # (content, artifact)
        result = result[0]
    if isinstance(result, list):
        result = "".join(b.get("text", "") if isinstance(b, dict) else getattr(b, "text", str(b)) for b in result)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"ok": False, "error": result}
    return result


class Toolbox:
    def __init__(self, tools):
        self.tools = {t.name: t for t in tools}
        self.calls: list[str] = []  # audit trail of tool names, in order

    async def call(self, name: str, **args) -> dict:
        self.calls.append(name)
        return _parse(await self.tools[name].ainvoke(args))

    @classmethod
    @asynccontextmanager
    async def open(cls):
        """Start the MCP server as a subprocess and keep one session open."""
        client = MultiServerMCPClient({
            "fiberlab": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", "fiberlab.mcp_server"],
                "env": dict(os.environ),
            }
        })
        async with client.session("fiberlab") as session:
            yield cls(await load_mcp_tools(session))
