"""External MCP tools for Chat On Steroids Settings > Plugins.

The ChatGPT conversation invokes tools; this server does NOT use ChatGPT
cookies, the browser DOM, an OpenAI API key, or unattended model inference.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

# CoS custom-executable plugins do not necessarily set a working directory.
# Allow `python C:\...\clipfarm_mcp\server.py` without an editable pip install.
_ROOT = Path(__file__).resolve().parents[1]
for _path in (str(_ROOT), str(_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from mcp.server.fastmcp import FastMCP  # MCP Python SDK v1
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP  # MCP Python SDK v2
from mcp.types import ImageContent

from clipfarm_mcp import core

mcp = FastMCP("ClipFarm", instructions=(
    "ClipFarm is a local, human-reviewed video clipping pipeline. "
    "Use get_transcript in pages before selecting highlights. "
    "Never claim a clip is guaranteed viral. Never publish without separate user authorization."
))


@mcp.tool()
def prepare_video(source_path: str = "", url: str = "", rights_confirmed: bool = False,
                  reframe_mode: str = "disabled") -> dict:
    """Queue a local video or permitted YouTube/Twitch/Kick URL for offline Whisper transcription.

    Local files must be under CLIPFARM_IMPORT_ROOT. Defaults to CPU-friendly
    fixed framing; choose auto only with compatible face-tracking MediaPipe.
    Only call with rights_confirmed when the user confirms ownership or
    permission to clip the source.
    """
    return core.prepare_video(source_path=source_path, url=url,
                              rights_confirmed=rights_confirmed, reframe_mode=reframe_mode)


@mcp.tool()
def list_pending(limit: int = 25) -> list[dict]:
    """List jobs awaiting ChatGPT clip selection or human approval."""
    return core.list_pending(limit)


@mcp.tool()
def get_job_status(job_id: str) -> dict:
    """Read local preparation or render state; use this for progress and errors."""
    return core.get_job_status(job_id)


@mcp.tool()
def get_transcript(job_id: str, offset: int = 0, limit: int = 250) -> dict:
    """Read timestamped words in pages; request successive offsets until next_offset is null."""
    return core.get_transcript(job_id, offset, limit)


@mcp.tool()
def get_video_frame(job_id: str, seconds: float, clip_index: int | None = None) -> ImageContent:
    """Get one bounded JPEG frame from source or a rendered clip for visual review."""
    return ImageContent(type="image", mimeType="image/jpeg",
                        data=base64.b64encode(core.get_frame(job_id, seconds, clip_index)).decode("ascii"))


@mcp.tool()
def submit_highlights(job_id: str, shorts: list[dict]) -> dict:
    """Submit up to 20 selected clips with start/end, viral_score, viral_reason,
    video_description_for_tiktok, video_description_for_instagram,
    video_title_for_youtube_short and viral_hook_text. Clips must be 10–75 sec,
    non-overlapping, inside video bounds and contain transcript words.
    """
    return core.submit_highlights(job_id, shorts)


@mcp.tool()
def render_job(job_id: str) -> dict:
    """Run local ClippyMe FFmpeg/reframe pipeline using the submitted selection; no Gemini call."""
    return core.render_job(job_id)


@mcp.tool()
def list_clips(job_id: str) -> list[dict]:
    """List completed on-disk clip files and their quality checks for review."""
    return core.list_clips(job_id)


@mcp.tool()
def approve_clips(job_id: str, clip_indices: list[int]) -> dict:
    """Record local human approval. This tool NEVER uploads, schedules, or publishes clips."""
    return core.approve_clips(job_id, clip_indices)


if __name__ == "__main__":
    mcp.run(transport="stdio")
