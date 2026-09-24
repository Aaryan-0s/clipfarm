"""Joke-aware v2 is an opt-in style and has separate audible rank cues."""
import json
import wave

import pytest

from clipfarm_mcp.styles import cartoon_ranked_joke_aware as style


def fixture_plan(tmp_path, monkeypatch):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"video fixture")
    monkeypatch.setattr(style.base, "length", lambda _: 500.0)
    preset = json.loads(style.PRESET.read_text(encoding="utf8"))
    plan = {"style_id": preset["style_id"], "clips": [
        {"rank": n, "source": str(source), "ranges": [[5.0, 17.0]]}
        for n in range(1, 6)
    ]}
    return plan, preset


def test_variable_joke_lengths_are_accepted(tmp_path, monkeypatch):
    plan, preset = fixture_plan(tmp_path, monkeypatch)
    plan["clips"][0]["ranges"] = [[5, 57]]
    plan["clips"][4]["ranges"] = [[5, 24]]
    assert [x["rank"] for x in style.validate_plan(plan, preset)] == [5, 4, 3, 2, 1]


def test_rejects_style_not_explicitly_selected(tmp_path, monkeypatch):
    plan, preset = fixture_plan(tmp_path, monkeypatch)
    plan["style_id"] = "cartoon_ranked_v1"
    with pytest.raises(ValueError, match="explicitly"):
        style.validate_plan(plan, preset)


def test_rejects_missing_footage_and_bad_ranges(tmp_path, monkeypatch):
    plan, preset = fixture_plan(tmp_path, monkeypatch)
    plan["clips"][1]["ranges"] = [[9, 8]]
    with pytest.raises(ValueError, match="Invalid source"):
        style.validate_plan(plan, preset)
    plan["clips"][1]["ranges"] = [[5, 17]]
    plan["clips"][1]["source"] = str(tmp_path / "missing.mp4")
    with pytest.raises(ValueError, match="Source missing"):
        style.validate_plan(plan, preset)


def test_separate_sounds_and_visual_reveal_are_present(tmp_path, monkeypatch):
    plan, preset = fixture_plan(tmp_path, monkeypatch)
    first = style.filter_graph(plan["clips"][4], preset, "rank_5.ass")
    next_clip = style.filter_graph(plan["clips"][3], preset, "rank_4.ass")
    assert "enable='gte(t,0.52)'" in first
    assert "adelay=520:all=1" in first
    assert "volume=0.000[swish]" in first
    assert "volume=0.650[swish]" in next_clip
    sound = style.create_rank_cue(tmp_path / "rank.wav")
    with wave.open(str(sound), "rb") as wav:
        assert wav.getframerate() == 48000
        assert .25 < wav.getnframes() / wav.getframerate() < .29
