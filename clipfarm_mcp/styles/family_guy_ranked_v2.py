"""Opt-in Family Guy ranked video: 2,3,4,5,1; typewriter; approved swish.

Usage: python -m clipfarm_mcp.styles.family_guy_ranked_v2 PLAN --output DIR
No changes are made to the previous Family Guy, football or streamer styles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import cartoon_ranked as base
from . import cartoon_ranked_joke_aware as legacy

PRESET = Path(__file__).parent / "presets" / "family_guy_ranked_v2.json"
ORDER = [2, 3, 4, 5, 1]
RATE = 48000
W, H = 720, 1280


def validate_plan(plan: dict, preset: dict) -> list[dict]:
    if plan.get("style_id") != preset["style_id"]:
        raise ValueError("The new Family Guy style must be explicitly selected")
    if plan.get("playback_order") != ORDER:
        raise ValueError("Required playback order is [2, 3, 4, 5, 1]")
    clips = plan.get("clips", [])
    if len(clips) != 5 or {c.get("rank") for c in clips} != set(ORDER):
        raise ValueError("Require exactly five unique ranks")
    by_rank = {c["rank"]: c for c in clips}
    for rank in ORDER:
        c = by_rank[rank]
        if not c.get("label") or c["label"] != preset["labels"][str(rank)]:
            raise ValueError(f"Label mismatch for rank {rank}")
        source = Path(c["source"])
        if not source.is_file():
            raise ValueError(f"Missing episode: {source}")
        duration = base.length(source)
        spans = c.get("ranges", [])
        if not spans:
            raise ValueError(f"Missing scene ranges for #{rank}")
        total = 0.0
        for a, b in spans:
            if not all(math.isfinite(float(x)) for x in (a, b)) or not 0 <= a < b <= duration:
                raise ValueError(f"Invalid scene range for #{rank}: {a}, {b}")
            total += b - a
        if not 7 <= total <= 65:
            raise ValueError(f"Scene #{rank} length invalid: {total:.2f}s")
    return [by_rank[r] for r in ORDER]


def asset_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def approved_swish(source: Path, expected_hash: str, assets: Path) -> tuple[Path, dict]:
    if not source.is_file():
        raise FileNotFoundError(f"Approved user swish is missing: {source}")
    actual = asset_sha256(source)
    if actual != expected_hash.upper():
        raise ValueError("Approved user swish SHA-256 has changed; stop instead of substituting")
    original = assets / "approved_transition_swish.mp3"
    shutil.copy2(source, original)
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(original),
         "-map", "0:a:0", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        check=True, capture_output=True,
    )
    samples = np.frombuffer(proc.stdout, dtype="<i2").copy()
    if not len(samples) or np.max(np.abs(samples.astype(np.float32))) < 100:
        raise ValueError("Approved swish is silent or unusable")
    peak = float(np.max(np.abs(samples.astype(np.float32))))
    index = int(np.flatnonzero(np.abs(samples.astype(np.float32)) >= max(280., peak * .07))[0])
    trimmed = samples[index:]
    dest = assets / "approved_swish_cut_aligned.wav"
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(trimmed.tobytes())
    return dest, {"original_file": str(source), "local_copy": str(original),
                  "sha256": actual, "trimmed_leading_silence_ms": round(index / RATE * 1000, 3),
                  "aligned_wav": str(dest), "duration_seconds": round(len(trimmed) / RATE, 3)}


def type_timing(label: str, preset: dict) -> tuple[float, float, float]:
    begin = float(preset.get("typing_delay", .16))
    duration = float(preset.get("typing_duration", 1.24))
    return begin, duration, duration / len(label)


def create_board(item: dict, previously_shown: set[int], preset: dict, assets: Path) -> Path:
    frame = base.frame_at(Path(item["source"]), item["ranges"][0][0] + .6)
    plate = ImageOps.fit(frame, (W, H)).filter(ImageFilter.GaussianBlur(42)).convert("RGBA")
    plate = Image.blend(plate, Image.new("RGBA", (W, H), "#ADC8C9"), .67)
    d = ImageDraw.Draw(plate, "RGBA")
    d.rectangle((0, 0, W, 317), fill=(242, 249, 246, 86))
    d.rectangle((0, 315, W, 322), fill=(24, 26, 30, 210))
    d.rectangle((0, 1102, W, 1108), fill=(24, 26, 30, 170))
    parts = [(p, c) for p, c in preset["title_line_1_parts"]]
    base.stylized_line(d, 24, 18, parts)
    parts = [(p, c) for p, c in preset["title_line_2_parts"]]
    base.stylized_line(d, 24, 70, parts)
    for rank in (1, 2, 3, 4, 5):
        y = preset["first_row_y"] + (rank - 1) * preset["row_spacing"]
        if rank == item["rank"]:
            d.rounded_rectangle((28, y - 2, 687, y + 32), radius=8,
                                fill=(15, 21, 25, 138))
        # The board's row positions never change. Existing labels persist.
        shown_label = preset["labels"][str(rank)] if rank in previously_shown else ""
        text = f"{rank}. {shown_label}"
        color = "#FFD847" if rank == item["rank"] else "#FFFFFF"
        base.outlined(d, (42, y), text, base.font(27, italic=False), color, sw=2)
    # Footer rather than across a face or a caption. Exact user-specified identity.
    font = base.font(30, italic=False)
    handle = "@clipshanger70"
    bbox = d.textbbox((0, 0), handle, font=font)
    x = (W - (bbox[2] - bbox[0])) // 2
    y = 1163
    d.text((x + 2, y + 2), handle, font=font, fill=(10, 15, 12, 160),
           stroke_width=2, stroke_fill=(8, 12, 11, 120))
    d.text((x, y), handle, font=font, fill=(177, 180, 62, 210),
           stroke_width=1, stroke_fill=(30, 35, 11, 210))
    dest = assets / f"rank_{item['rank']}_board.png"
    plate.convert("RGB").save(dest)
    return dest


def append_typing_ass(subtitles: Path, label: str, seconds: float, preset: dict) -> list[float]:
    raw = subtitles.read_text(encoding="utf-8-sig")
    rank_style = (
        "Style: Rank,Arial,27,&H0047D8FF,&H0047D8FF,&H00151515,&H60000000,"
        "-1,0,0,0,100,100,0,0,1,2,1,7,0,0,0,1\n"
    )
    raw = raw.replace("[Events]", rank_style + "[Events]", 1)
    start, duration, interval = type_timing(label, preset)
    pos = (82, preset["first_row_y"] + (int(preset["active_rank"]) - 1) * preset["row_spacing"] + 3)
    text_pos = "{\\an7\\pos(%d,%d)}" % pos
    timings = []
    for idx in range(1, len(label) + 1):
        begin = start + (idx - 1) * interval
        end = start + idx * interval if idx < len(label) else seconds
        timings.append(begin)
        raw += ("Dialogue: 3," + base.ass_time(begin) + "," + base.ass_time(end) +
                ",Rank,,0,0,0,," + text_pos + label[:idx].replace("{", "(").replace("}", ")") + "\n")
    subtitles.write_text(raw, encoding="utf-8-sig")
    return timings


def typing_audio(times: list[float], seconds: float, destination: Path) -> None:
    n = int((seconds + .05) * RATE)
    buffer = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(20260926)
    duration = int(.033 * RATE)
    t = np.arange(duration, dtype=np.float64) / RATE
    envelope = (1 - np.exp(-t * 1400)) * np.exp(-t * 105)
    for index, sec in enumerate(times):
        at = int(sec * RATE)
        if at + duration >= n:
            continue
        click = (rng.standard_normal(duration) * .46 +
                 np.sin(2*np.pi*(1080 + index % 5 * 83)*t) * .18) * envelope
        buffer[at:at+duration] += (click * .32).astype(np.float32)
    pcm = np.clip(buffer, -.9, .9)
    with wave.open(str(destination), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((pcm * 32767).astype("<i2").tobytes())


def original_subtitle_captions(item: dict, destination: Path) -> int:
    """Map the episode's authored SRT cues to the selected local clip ranges.

    Prefer the authored dialogue when the MKV contains an English subtitle
    stream. Avoid a model hallucinating Stewie's deliberately repeated words.
    """
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-i", str(item["source"]), "-map", "0:s:0", "-f", "srt", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode:
        return 0

    def seconds(stamp: str) -> float:
        h, m, last = stamp.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(last)

    events = []
    for block in re.split(r"\n\s*\n", proc.stdout.replace("\r\n", "\n")):
        match = re.search(r"(\d\d:\d\d:\d\d,\d{3})\s+-->\s+"
                          r"(\d\d:\d\d:\d\d,\d{3})", block)
        if not match:
            continue
        a, b = seconds(match.group(1)), seconds(match.group(2))
        body = block[match.end():].strip()
        body = re.sub(r"<[^>]*>", "", body)
        body = re.sub(r"\{[^}]+\}", "", body)
        body = re.sub(r"\s+", " ", body).strip().replace("&amp;", "&")
        if not body:
            continue
        offset = 0.0
        for lo, hi in item["ranges"]:
            start, end = max(a, lo), min(b, hi)
            if end - start >= .09:
                events.append((offset + start - lo, offset + end - lo, body))
            offset += hi - lo
    if not events:
        return 0
    script = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 720", "PlayResY: 1280",
        "WrapStyle: 2", "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Dialogue,Arial,42,&H00FFFFFF,&H00FFFFFF,&H00121212,&H60000000,-1,0,0,0,100,100,0,0,1,3,1,2,32,32,237,1",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    for a, b, body in events:
        # Full source subtitles, but strip markup and escape ASS metacharacters.
        body = body.replace("{", "(").replace("}", ")").replace("\\", "/")
        script.append(f"Dialogue: 0,{base.ass_time(a)},{base.ass_time(b)},"
                      f"Dialogue,,0,0,0,,{body}")
    destination.write_text("\n".join(script) + "\n", encoding="utf-8-sig")
    return len(events)


def render_segment(item: dict, source: Path, board: Path, subtitles: Path,
                   swish: Path, typing: Path, dest: Path, assets: Path,
                   preset: dict, first: bool) -> float:
    seconds = base.length(source)
    gain = 0.0 if first else float(preset["swish_gain"])
    graph = (
        "[0:v]fps=24,split=2[soft_src][sharp_src];"
        "[soft_src]scale=720:780:force_original_aspect_ratio=increase,crop=720:780,"
        "boxblur=20:2[soft];"
        "[sharp_src]scale=720:780:force_original_aspect_ratio=decrease,setsar=1[sharp];"
        "[soft][sharp]overlay=(W-w)/2:(H-h)/2:shortest=1[scene];"
        "[1:v]format=yuv420p[back];"
        "[back][scene]overlay=0:322:shortest=1,format=yuv420p,"
        f"ass=filename={subtitles.name}[v];"
        "[0:a]aresample=48000,volume=.90[dialogue];"
        f"[2:a]aresample=48000,volume={gain:.3f}[transition];"
        "[3:a]aresample=48000,volume=.84[keys];"
        "[dialogue][transition][keys]amix=inputs=3:duration=first:normalize=0,"
        "alimiter=limit=0.94[a]"
    )
    base.call(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-i", str(source), "-loop", "1", "-framerate", "24", "-i", str(board),
               "-i", str(swish), "-i", str(typing), "-filter_complex", graph,
               "-map", "[v]", "-map", "[a]", "-t", str(seconds), "-r", "24",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
               "-ac", "2", "-movflags", "+faststart", str(dest)], cwd=assets)
    actual = base.length(dest)
    if abs(actual - seconds) > .5:
        raise RuntimeError(f"Duration changed unexpectedly for rank {item['rank']}")
    return actual


def create_thumbnail(plan: dict, preset: dict, output: Path) -> Path:
    by_rank = {c["rank"]: c for c in plan["clips"]}
    source = by_rank[1]
    # The image is an actual frame from this compilation's final episode.
    shot = base.frame_at(Path(source["source"]), float(preset["thumbnail_source_second"]))
    im = ImageOps.fit(shot.convert("RGB"), (1280, 720), method=Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, 1280, 170), fill=(176, 18, 25, 246))
    d.rectangle((0, 167, 1280, 179), fill=(40, 11, 11, 255))
    title = "TOP 5 STEWIE MOMENTS"
    font_size = 79
    while font_size > 49:
        f = base.font(font_size)
        if d.textbbox((0, 0), title, font=f)[2] < 1215:
            break
        font_size -= 2
    box = d.textbbox((0, 0), title, font=f)
    d.text(((1280 - box[2]) // 2, 30), title, font=f, fill=(255, 255, 255, 255),
           stroke_width=5, stroke_fill=(24, 16, 16, 255))
    d.rounded_rectangle((30, 605, 286, 688), radius=16, fill=(181, 17, 32, 238))
    d.text((56, 613), "TOP 5", font=base.font(53), fill="white",
           stroke_width=3, stroke_fill="#171717")
    d.rounded_rectangle((912, 634, 1258, 695), radius=14, fill=(18, 23, 22, 167))
    d.text((930, 640), "@clipshanger70", font=base.font(32, italic=False),
           fill=(201, 216, 83, 255), stroke_width=1, stroke_fill="#141917")
    dest = output / "thumbnail_1280x720.png"
    im.save(dest)
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preset", type=Path, default=PRESET)
    parser.add_argument("--whisper-model", default="base", choices=["tiny", "base", "small"])
    args = parser.parse_args()
    preset = json.loads(args.preset.read_text(encoding="utf-8-sig"))
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    ordered = validate_plan(plan, preset)
    args.output.mkdir(parents=True, exist_ok=True)
    art = args.output / "_style_assets"
    art.mkdir(exist_ok=True)
    (args.output / "source_plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )
    (art / "preset_snapshot.json").write_text(json.dumps(preset, indent=2), encoding="utf8")
    swish, swish_info = approved_swish(Path(preset["approved_swish_path"]),
                                       preset["approved_swish_sha256"], art)
    from faster_whisper import WhisperModel
    whisper = None
    revealed: set[int] = set()
    results = []
    boundary = 0.0
    for index, item in enumerate(ordered):
        rank = item["rank"]
        source = legacy.episode_clip(item, art, preset["fps"], preset)
        seconds = base.length(source)
        board = create_board(item, revealed, preset, art)
        subtitles = art / f"rank_{rank}_captions_and_typing.ass"
        subtitle_count = original_subtitle_captions(item, subtitles)
        if subtitle_count:
            print(f"Episode subtitles for #{rank}: {subtitle_count} cues", flush=True)
        else:
            if whisper is None:
                whisper = WhisperModel(args.whisper_model, device="cpu", compute_type="int8")
            base.ass_caption_file(source, subtitles, model=whisper)
        typing_preset = {**preset, "active_rank": rank}
        times = append_typing_ass(subtitles, item["label"], seconds, typing_preset)
        typing = art / f"rank_{rank}_typing.wav"
        typing_audio(times, seconds, typing)
        dest = args.output / f"{index+1:02d}_rank_{rank}_{item['file_tag']}.mp4"
        actual = render_segment(item, source, board, subtitles, swish, typing,
                                dest, art, preset, first=(index == 0))
        results.append({"rank": rank, "episode_id": item.get("episode_id"),
                        "source": item["source"], "ranges": item["ranges"],
                        "label": item["label"], "cut_reason": item["cut_reason"],
                        "seconds": round(actual, 3), "file": str(dest),
                        "starts_at_seconds": round(boundary, 3),
                        "typing_starts_at_seconds": round(boundary + times[0], 3),
                        "typing_events": len(times), "swish_at_start": index > 0})
        boundary += actual
        revealed.add(rank)
        print(f"DONE #{rank}: {actual:.2f}s | {dest.name}", flush=True)
    join_file = art / "join_in_playback_order.txt"
    join_file.write_text("".join(f"file '{Path(x['file']).resolve().as_posix()}'\n"
                                 for x in results), encoding="utf8")
    final = args.output / preset["output_filename"]
    # Re-encode the joined timeline so independently encoded H.264 segments
    # cannot produce duplicate/non-monotonic DTS at scene-change boundaries.
    base.call(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "concat", "-safe", "0", "-i", str(join_file),
               "-map", "0:v:0", "-map", "0:a:0", "-vf", "fps=24,format=yuv420p",
               "-af", "aresample=48000:async=1:first_pts=0",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
               "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
               "-movflags", "+faststart", str(final)])
    thumbnail = create_thumbnail(plan, preset, args.output)
    transitions = [{"from_rank": results[i-1]["rank"], "to_rank": results[i]["rank"],
                    "scene_cut_at_seconds": results[i]["starts_at_seconds"],
                    "sfx_attack_at_seconds": results[i]["starts_at_seconds"]}
                   for i in range(1, 5)]
    manifest = {"style_id": preset["style_id"], "playback_order": ORDER,
                "title": plan["title"], "watermark": "@clipshanger70",
                "approved_swish": swish_info, "swishes": transitions,
                "swish_count": 4, "typing_sequences": 5, "clips": results,
                "duration_seconds": round(base.length(final), 3),
                "thumbnail": str(thumbnail),
                "source_plan": str(args.output / "source_plan.json"),
                "final": str(final), "publication": "manual_review_only"}
    (args.output / "render_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
    print(f"FINAL: {final} | {manifest['duration_seconds']} seconds", flush=True)


if __name__ == "__main__":
    main()
