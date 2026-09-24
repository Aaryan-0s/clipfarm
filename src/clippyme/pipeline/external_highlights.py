"""Validated, local handoff from a ChatGPT/MCP conversation to the render pipeline.

Neither this module nor the caller invokes an AI service.  This is a *file*
handoff, deliberately not a browser-session scraper or an inference API.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from clippyme.schemas import ViralClipsResponse
from clippyme.pipeline.gemini_parser import (
    backfill_hook_text,
    drop_wordless_clips,
    validate_and_dedupe,
)

MAX_TRANSCRIPT_BYTES = 32 * 1024 * 1024
MAX_HIGHLIGHTS_BYTES = 128 * 1024


def _json_object(path: str, max_bytes: int) -> dict:
    p = Path(path)
    if not p.is_file() or p.stat().st_size > max_bytes or p.stat().st_size == 0:
        raise ValueError(f"missing, empty, or oversized JSON input: {p.name}")
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON input: {p.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {p.name}")
    return value


def load_transcript_file(path: str) -> dict:
    """Require word timestamps, not arbitrary text that cannot be cut safely."""
    transcript = _json_object(path, MAX_TRANSCRIPT_BYTES)
    segments = transcript.get("segments")
    if not isinstance(segments, list) or len(segments) > 100_000:
        raise ValueError("transcript must contain a bounded segments array")
    word_count = 0
    previous_start = -1.0
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("words"), list):
            raise ValueError("every transcript segment must have a words array")
        for word in segment["words"]:
            if not isinstance(word, dict):
                raise ValueError("transcript word must be an object")
            try:
                start, end = float(word["start"]), float(word["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("transcript words require numeric start/end") from exc
            if not all(map(math.isfinite, (start, end))) or start < 0 or end <= start:
                raise ValueError("transcript has invalid word timestamps")
            if start < previous_start - 0.25:
                raise ValueError("transcript words must be chronological")
            previous_start = start
            word_count += 1
            if word_count > 250_000:
                raise ValueError("transcript exceeds word limit")
    if not word_count:
        raise ValueError("transcript has no timestamped words")
    return transcript


def validate_selection(payload: dict, transcript: dict, duration: float) -> dict:
    """Validate every candidate before rendering; never silently fall back to Gemini."""
    if not isinstance(payload, dict):
        raise ValueError("highlights must be a JSON object")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("source duration is unavailable")
    # Fail the complete handoff on an invalid clip, instead of silently
    # publishing a different subset than ChatGPT/user approved.
    try:
        validated = ViralClipsResponse.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"invalid highlights: {exc}") from exc
    if not validated.shorts:
        raise ValueError("select at least one clip")
    for clip in validated.shorts:
        if not math.isfinite(clip.start) or not math.isfinite(clip.end):
            raise ValueError("clip timestamps must be finite")
        if clip.end > duration + 0.5:
            raise ValueError("clip extends beyond the source video")
    clips = validate_and_dedupe(validated.model_dump(), video_duration=duration)
    if len(clips) != len(validated.shorts):
        raise ValueError("overlapping or duplicate clips in selection")
    intervals = sorted((c["start"], c["end"]) for c in clips)
    if any(right[0] < left[1] for left, right in zip(intervals, intervals[1:])):
        raise ValueError("clips must not overlap")
    words = [w for seg in transcript["segments"] for w in seg["words"]]
    if len(drop_wordless_clips(clips, words)) != len(clips):
        raise ValueError("one or more clips contain no timestamped transcript words")
    backfill_hook_text(clips, words)
    return {"shorts": clips, "analysis_provider": "chatgpt_mcp_handoff"}


def load_highlights_file(path: str, transcript: dict, duration: float) -> dict:
    return validate_selection(_json_object(path, MAX_HIGHLIGHTS_BYTES), transcript, duration)
