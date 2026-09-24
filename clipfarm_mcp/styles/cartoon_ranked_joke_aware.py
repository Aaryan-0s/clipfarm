"""Opt-in v2 cartoon countdown: variable joke-length cuts, separate rank + swish cues.

This module neither changes the legacy ClipFarm engine nor the v1 renderer.
Usage: python -m clipfarm_mcp.styles.cartoon_ranked_joke_aware PLAN --output DIR
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import cartoon_ranked as base

PRESET = Path(__file__).parent / "presets" / "cartoon_ranked_joke_aware_v2.json"


def validate_plan(plan: dict, preset: dict) -> list[dict]:
    if plan.get("style_id") != preset["style_id"]:
        raise ValueError("Joke-aware style must be explicitly selected")
    clips = plan.get("clips", [])
    if len(clips) != 5 or {item.get("rank") for item in clips} != {1, 2, 3, 4, 5}:
        raise ValueError("Exactly five unique ranked clips required")
    for item in clips:
        source = Path(item["source"])
        if not source.is_file():
            raise ValueError(f"Source missing: {source}")
        intervals = item.get("ranges", [])
        if not intervals:
            raise ValueError("Clip needs source ranges")
        total = 0.0
        source_length = base.length(source)
        for a, b in intervals:
            if not (math.isfinite(float(a)) and math.isfinite(float(b))
                    and 0 <= float(a) < float(b) <= source_length):
                raise ValueError(f"Invalid source timestamp in rank {item['rank']}")
            total += b - a
        if not preset["minimum_clip_seconds"] <= total <= preset["maximum_clip_seconds"]:
            raise ValueError(f"Rank {item['rank']} outside 8–65 seconds: {total:.2f}")
    return sorted(clips, key=lambda i: -i["rank"])


def create_backplates(item: dict, preset: dict, art: Path) -> tuple[Path, Path]:
    """The current ranking row appears 0.52s into each scene, with an audible cue."""
    original_frame = base.frame_at(Path(item["source"]), item["ranges"][0][0] + .5)
    w, h = preset["width"], preset["height"]
    im = ImageOps.fit(original_frame, (w, h)).filter(ImageFilter.GaussianBlur(48)).convert("RGBA")
    palette = {5: "#DFB9A0", 4: "#B0CFD8", 3: "#C9DBC6", 2: "#D9C8D6", 1: "#B3D7D9"}
    im = Image.blend(im, Image.new("RGBA", (w, h), palette[item["rank"]]), .65)
    paths = []
    for is_revealed in (False, True):
        plate = im.copy()
        d = ImageDraw.Draw(plate, "RGBA")
        d.rectangle((0, 0, w, 317), fill=(245, 249, 248, 67))
        d.rectangle((0, 315, w, 322), fill=(20, 23, 26, 165))
        d.rectangle((0, 1102, w, 1108), fill=(20, 23, 26, 155))
        base.stylized_line(d, 24, 20, [("RANKING ", "#FFFFFF"), ("TOP 5 ", "#FF9839"),
                                        ("TIMES ", "#FFFFFF"), ("PETER", "#FF9839")])
        base.stylized_line(d, 24, 72, [("GOT ", "#FFFFFF"), ("HARASSED", "#5CE17C")])
        for rank in range(1, 6):
            y = preset["first_row_y"] + (rank - 1) * preset["row_spacing"]
            active = rank == item["rank"] and is_revealed
            reveal = rank > item["rank"] or active
            if active:
                d.rounded_rectangle((29, y-2, 684, y+32), radius=7, fill=(13, 16, 21, 125))
            text = f"{rank}. " + (preset["labels"][str(rank)] if reveal else "")
            base.outlined(d, (42, y), text, base.font(27, italic=False),
                          "#FFD847" if active else "#FFFFFF", sw=2)
        target = art / f"rank_{item['rank']}_{'shown' if is_revealed else 'waiting'}.png"
        plate.convert("RGB").save(target)
        paths.append(target)
    return paths[0], paths[1]


def create_rank_cue(path: Path) -> Path:
    """Create an original 0.27s bright rank-reveal tick; separate from the swish."""
    sample_rate = 48000
    n = int(sample_rate * .27)
    t = np.arange(n, dtype=np.float64) / sample_rate
    envelope = (1 - np.exp(-t * 180)) * np.exp(-t * 18)
    tone = (np.sin(2*np.pi*(740*t + 350*t*t)) * .55 +
            np.sin(2*np.pi*(1110*t + 550*t*t)) * .26 +
            np.sin(2*np.pi*(1480*t + 400*t*t)) * .14)
    signal = envelope * tone
    signal = signal * (0.68/max(.001, float(np.max(np.abs(signal)))))
    pcm = (np.clip(signal, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return path


def filter_graph(item: dict, preset: dict, ass_filename: str) -> str:
    """Each rank gets an audible reveal; all but the first get a separate swish."""
    swish_gain = float(preset["swish_gain"]) if item["rank"] < 5 else 0
    reveal_ms = int(round(preset["rank_reveal_seconds"]*1000))
    visual = (
        "[0:v]fps=24,scale=720:780:force_original_aspect_ratio=increase,"
        "crop=720:780,setsar=1[scene];"
        "[1:v]format=yuv420p[waiting];[2:v]format=yuv420p[shown];"
        f"[waiting][shown]overlay=0:0:enable='gte(t,{preset['rank_reveal_seconds']})':"
        "shortest=1[board];"
        "[board][scene]overlay=0:322:shortest=1,format=yuv420p,"
        f"ass=filename={ass_filename}[v]"
    )
    audio = (
        ";[0:a]aresample=48000,volume=0.91[dialogue];"
        f"[3:a]aresample=48000,volume={swish_gain:.3f}[swish];"
        f"[4:a]aresample=48000,adelay={reveal_ms}:all=1,"
        f"volume={float(preset['rank_cue_gain']):.3f}[rank_cue];"
        "[dialogue][swish][rank_cue]amix=inputs=3:duration=first:normalize=0,"
        "alimiter=limit=0.92[a]"
    )
    return visual + audio


def render(item: dict, src: Path, waiting: Path, shown: Path, subtitles: Path,
           swish: Path, tick: Path, dest: Path, art: Path, preset: dict) -> dict:
    seconds = base.length(src)
    if not preset["minimum_clip_seconds"]-.5 <= seconds <= preset["maximum_clip_seconds"]+.5:
        raise ValueError(f"Extracted source violates per-style limits: {seconds:.2f}")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(src), "-loop", "1", "-framerate", "24", "-i", str(waiting),
           "-loop", "1", "-framerate", "24", "-i", str(shown),
           "-i", str(swish), "-i", str(tick),
           "-filter_complex", filter_graph(item, preset, subtitles.name),
           "-map", "[v]", "-map", "[a]", "-t", str(seconds), "-r", "24",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(dest)]
    base.call(cmd, cwd=art)
    actual = base.length(dest)
    if abs(seconds-actual) > .5:
        raise RuntimeError(f"Rendered duration unexpected for #{item['rank']}")
    return {"rank": item["rank"], "seconds": round(actual, 2), "file": str(dest),
            "ranges": item["ranges"], "cut_reason": item["cut_reason"],
            "rank_reveal_cue_seconds": preset["rank_reveal_seconds"],
            "swish_at_next_clip_start": item["rank"] < 5}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--whisper-model", choices=["tiny", "base", "small"], default="base")
    args = ap.parse_args()
    preset = json.loads(PRESET.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    clips = validate_plan(plan, preset)
    args.output.mkdir(parents=True, exist_ok=True)
    art = args.output / "_style_assets"
    art.mkdir(exist_ok=True)
    (art / "preset_snapshot.json").write_text(json.dumps(preset, indent=2), encoding="utf-8")
    swish = base.whoosh(art / "original_swisshhh.wav", .44)
    cue = create_rank_cue(art / "rank_reveal_tick.wav")
    from faster_whisper import WhisperModel
    model = WhisperModel(args.whisper_model, device="cpu", compute_type="int8")
    results = []
    for item in clips:
        src = base.episode_clip(item, art, preset["fps"])
        waiting, shown = create_backplates(item, preset, art)
        subtitles = art / f"rank_{item['rank']}.ass"
        base.ass_caption_file(src, subtitles, model=model)
        dest = args.output / f"{item['rank']}_{item['file_tag']}_joke_aware.mp4"
        metadata = render(item, src, waiting, shown, subtitles, swish, cue, dest, art, preset)
        results.append(metadata)
        print(f"Rank #{item['rank']}: {metadata['seconds']:.2f}s, swish={metadata['swish_at_next_clip_start']}, rank cue=YES", flush=True)
    join = art / "concat.txt"
    join.write_text("".join(f"file '{Path(m['file']).resolve().as_posix()}'\n" for m in results), encoding="utf-8")
    final = args.output / "Top_5_Peter_Joke_Aware_with_Rank_SFX.mp4"
    base.call(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "concat", "-safe", "0", "-i", str(join), "-c", "copy",
               "-movflags", "+faststart", str(final)])
    record = {"style_id": preset["style_id"], "intro_seconds": 0,
              "rank_cue_count": 5, "swish_count": 4, "clips": results,
              "duration": round(base.length(final), 2), "final": str(final),
              "publication": "manual_review_only"}
    (args.output / "render_manifest.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"FINAL: {final} ({record['duration']}s)", flush=True)


if __name__ == "__main__":
    main()
