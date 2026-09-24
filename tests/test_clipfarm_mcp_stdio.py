"""Exercise the real stdio MCP protocol, not just Python tool wrappers."""
import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_plugin_lists_tools_and_executes_read_only_call(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["CLIPFARM_DATA_DIR"] = str(tmp_path / "jobs-home")

    async def probe():
        spec = StdioServerParameters(command=sys.executable,
                                     args=[str(root / "clipfarm_mcp" / "server.py")],
                                     cwd=tmp_path, env=env)
        async with stdio_client(spec) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert {"prepare_video", "get_transcript", "submit_highlights", "render_job",
                        "list_clips", "approve_clips", "get_video_frame"}.issubset(names)
                result = await session.call_tool("list_pending", {"limit": 10})
                assert not getattr(result, "is_error", getattr(result, "isError", False))

    asyncio.run(probe())
