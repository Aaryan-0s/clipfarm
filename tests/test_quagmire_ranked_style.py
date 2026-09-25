"""The Quagmire style is separate from Peter and other future templates."""
import json
from pathlib import Path

from clipfarm_mcp.styles import cartoon_ranked_joke_aware as style


PRESET = Path(__file__).resolve().parents[1] / "clipfarm_mcp" / "styles" / "presets" / "quagmire_ranked_v1.json"


def test_quagmire_preset_is_opt_in_and_does_not_replace_peter_preset():
    cartoon = json.loads(style.PRESET.read_text(encoding="utf8"))
    quagmire = json.loads(PRESET.read_text(encoding="utf8"))
    assert quagmire["style_id"] != cartoon["style_id"]
    assert quagmire["preserve_source_aspect"] is True
    assert "QUAGMIRE" in "".join(part[0] for part in quagmire["title_line_2_parts"])
    assert "PETER" not in "".join(part[0] for part in quagmire["title_line_1_parts"])
    assert quagmire["output_filename"] == "Top_5_Funniest_Quagmire_Moments.mp4"
    assert cartoon["labels"]["1"] == "Hypnosis backfires"


def test_preserved_aspect_uses_source_sharp_and_blurred_stage():
    preset = json.loads(PRESET.read_text(encoding="utf8"))
    graph = style.filter_graph({"rank": 4}, preset, "rank_4.ass")
    assert "[sharp_src]scale=720:780:force_original_aspect_ratio=decrease" in graph
    assert "boxblur=20:2" in graph
    assert "adelay=520:all=1" in graph
    assert "volume=0.650[swish]" in graph
