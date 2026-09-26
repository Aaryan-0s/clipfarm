"""The new Family Guy ranked style is opt-in and must retain its own timing."""
import json
import wave

import numpy as np
import pytest

from clipfarm_mcp.styles import family_guy_ranked_v2 as style
from clipfarm_mcp.styles import cartoon_ranked_joke_aware as legacy


def preset():
    return json.loads(style.PRESET.read_text(encoding="utf8"))


def test_v2_does_not_override_old_peter_style():
    p = preset()
    old = json.loads(legacy.PRESET.read_text(encoding="utf8"))
    assert p["style_id"] == "family_guy_ranked_v2"
    assert p["style_id"] != old["style_id"]
    assert p["playback_order"] == [2, 3, 4, 5, 1]
    assert p["watermark"] == "@clipshanger70"
    assert "original_swisshhh" not in json.dumps(p)


def test_wrong_order_cannot_render():
    data = {"style_id": "family_guy_ranked_v2", "playback_order": [5, 4, 3, 2, 1]}
    with pytest.raises(ValueError, match="playback order"):
        style.validate_plan(data, preset())


def test_sfx_missing_does_not_trigger_old_swish(tmp_path):
    with pytest.raises(FileNotFoundError, match="Approved user swish"):
        style.approved_swish(tmp_path / "missing.mp3", "ABC", tmp_path)


def test_rank_typing_writes_per_character_events_and_sound(tmp_path):
    ass = tmp_path / "typing.ass"
    ass.write_text("[V4+ Styles]\n[Events]\n", encoding="utf8")
    p = {**preset(), "active_rank": 2}
    starts = style.append_typing_ass(ass, "STEWIE", 8., p)
    text = ass.read_text(encoding="utf-8-sig")
    assert len(starts) == 6
    assert starts[0] == pytest.approx(.16)
    assert text.count("Dialogue: 3,") == 6
    assert "STEWIE" in text
    file = tmp_path / "typing.wav"
    style.typing_audio(starts, 8., file)
    with wave.open(str(file), "rb") as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
        assert wav.getframerate() == 48000
        assert np.max(abs(samples)) > 100
        assert not np.any(samples[:int(.12 * 48000)])
