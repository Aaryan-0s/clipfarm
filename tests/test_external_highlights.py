"""Pure, no-paid-API selection handoff tests."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from clippyme.pipeline.external_highlights import (
    load_highlights_file, load_transcript_file, validate_selection,
)


def transcript_fixture():
    return {"text": "sample " * 100,
            "segments": [{"start": 0.0, "end": 50.0, "text": "sample " * 100,
                          "words": [{"word": "sample", "start": i * 0.5,
                                     "end": i * 0.5 + 0.4} for i in range(100)]}]}


def clip(start=3.0, end=25.0):
    return {"start": start, "end": end, "viral_score": 74,
            "viral_reason": "The speaker gives a concrete answer with a complete payoff.",
            "video_description_for_tiktok": "A complete insight.",
            "video_description_for_instagram": "A complete insight.",
            "video_title_for_youtube_short": "A surprising point",
            "viral_hook_text": "An interesting answer"}


def test_selection_without_api_and_backfilled_hook():
    selection = validate_selection({"shorts": [clip()]}, transcript_fixture(), 50.0)
    assert selection["analysis_provider"] == "chatgpt_mcp_handoff"
    assert selection["shorts"][0]["start"] == 3.0
    assert "cost_analysis" not in selection


@pytest.mark.parametrize("bad", [
    {"shorts": []},
    {"shorts": [clip(3, 6)]},
    {"shorts": [clip(45, 65)]},
    {"shorts": [clip(3, 25), clip(3, 25)]},
    {"shorts": [clip(3, 25), clip(3, float("inf"))]},
])
def test_bad_selection_fails_closed(bad):
    with pytest.raises(ValueError):
        validate_selection(bad, transcript_fixture(), 50.0)


def test_transcript_file_validation(tmp_path):
    path = tmp_path / "transcript.json"
    path.write_text(json.dumps(transcript_fixture()), encoding="utf-8")
    assert len(load_transcript_file(str(path))["segments"][0]["words"]) == 100
    path.write_text(json.dumps({"segments": [{"words": [{"start": -1, "end": 0}]}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_transcript_file(str(path))


def test_highlights_file_requires_valid_json(tmp_path):
    path = tmp_path / "highlights.json"
    path.write_text("{untrusted", encoding="utf-8")
    with pytest.raises(ValueError):
        load_highlights_file(str(path), transcript_fixture(), 50.0)
    path.write_text(json.dumps({"shorts": [clip()]}), encoding="utf-8")
    assert load_highlights_file(str(path), transcript_fixture(), 50.0)["shorts"]


def test_orchestrator_external_args_and_rejects_mixing():
    from clippyme.pipeline import orchestrator

    args = orchestrator._parse_args(["--input", "source.mp4", "--output", "output",
                                     "--transcript-file", "words.json", "--highlights-file", "clips.json"])
    orchestrator._configure_overrides(args)
    assert args.highlights_file == "clips.json"
    with pytest.raises(ValueError):
        orchestrator._configure_overrides(SimpleNamespace(**{**vars(args), "model": "gemini-3.5-flash"}))
    with pytest.raises(ValueError):
        orchestrator._configure_overrides(SimpleNamespace(**{**vars(args), "transcript_file": None}))
