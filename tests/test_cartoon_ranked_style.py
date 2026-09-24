"""Tests for the opt-in preset. The default ClipFarm renderer remains untouched."""
import json
import wave

import pytest

from clipfarm_mcp.styles import cartoon_ranked as style


def plan_fixture(tmp_path, monkeypatch):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"fixture source")
    monkeypatch.setattr(style, "length", lambda path: 999.0)
    preset = json.loads(style.PRESET.read_text(encoding="utf-8"))
    plan = {"style_id": "cartoon_ranked_v1", "clips": [
        {"rank": rank, "source": str(video), "ranges": [[10.0, 37.0]], "label": f"Moment {rank}"}
        for rank in range(1, 6)
    ]}
    return plan, preset


def test_style_opt_in_validation(tmp_path, monkeypatch):
    plan, preset = plan_fixture(tmp_path, monkeypatch)
    assert [c["rank"] for c in style.validate_plan(plan, preset)] == [5, 4, 3, 2, 1]
    plan["style_id"] = "other_style"
    with pytest.raises(ValueError, match="explicitly"):
        style.validate_plan(plan, preset)


def test_duration_and_source_guards(tmp_path, monkeypatch):
    plan, preset = plan_fixture(tmp_path, monkeypatch)
    plan["clips"][0]["ranges"] = [[10, 30]]
    with pytest.raises(ValueError, match="25–30"):
        style.validate_plan(plan, preset)
    plan["clips"][0]["ranges"] = [[10, 37]]
    plan["clips"][0]["source"] = str(tmp_path / "missing.mp4")
    with pytest.raises(ValueError, match="Missing source"):
        style.validate_plan(plan, preset)


def test_whoosh_original_audio(tmp_path):
    out = style.whoosh(tmp_path / "created.wav")
    with wave.open(str(out), "rb") as f:
        assert f.getframerate() == 48000
        assert f.getnchannels() == 1
        assert 0.34 < f.getnframes() / f.getframerate() < 0.38


def test_legacy_renderer_has_no_preset_dependency():
    from clipfarm_mcp import core
    assert core.prepare_video.__defaults__ is None  # Keyword-only defaults retained.
    assert "cartoon_ranked_v1" not in core.prepare_video.__code__.co_consts
