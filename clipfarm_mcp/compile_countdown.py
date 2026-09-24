"""Render a reviewed multi-episode countdown from local files, without API calls."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = (720, 1280)
FONT_BOLD = Path("C:/Windows/Fonts/arialbd.ttf")
FONT_HEAVY = Path("C:/Windows/Fonts/impact.ttf")


def _font(size: int, heavy: bool = False):
    return ImageFont.truetype(str(FONT_HEAVY if heavy else FONT_BOLD), size)


def _center(draw, at_y: int, message: str, font, fill):
    bb = draw.textbbox((0, 0), message, font=font)
    draw.text(((720 - (bb[2] - bb[0])) / 2, at_y), message, font=font, fill=fill,
              stroke_width=1, stroke_fill=(0, 0, 0, 150))


def make_overlay(destination: Path, item: dict) -> None:
    im = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 30, 700, 308), radius=34, fill=(13, 17, 32, 221))
    _center(d, 55, "FAMILY GUY  /  TOP 5", _font(32), "#FFDA63")
    _center(d, 90, "PETER GETTING HARASSED", _font(38), "#FFFFFF")
    _center(d, 135, f"#{item['rank']}", _font(138, True), "#FFDA63")
    d.rounded_rectangle((24, 952, 696, 1136), radius=26, fill=(13, 17, 32, 224))
    label = item["label"].upper()
    font = _font(44)
    while d.textbbox((0, 0), label, font=font)[2] > 640 and font.size > 23:
        font = _font(font.size - 2)
    _center(d, 984, label, font, "#FFFFFF")
    _center(d, 1062, f"SEASON {item['season']:02d}  |  EPISODE {item['episode']:02d}",
            _font(26), "#FFDA63")
    im.save(destination)


def make_intro(destination: Path, complete: bool) -> None:
    im = Image.new("RGB", SIZE, "#141923")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((40, 370, 680, 914), radius=48, fill="#212C40")
    _center(d, 410, "FAMILY GUY", _font(40), "#FFDA63")
    _center(d, 468, "TOP 5", _font(140, True), "#FFFFFF")
    _center(d, 650, "PETER GETTING", _font(54), "#FFFFFF")
    _center(d, 716, "HARASSED", _font(67, True), "#FFDA63")
    if not complete:
        _center(d, 830, "DRAFT / FINAL SCENE PENDING", _font(26), "#FFFFFF")
    im.save(destination)


def run(command: list[str]) -> None:
    proc = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, errors="replace")
    if proc.returncode:
        raise RuntimeError(f"FFmpeg failed ({proc.returncode}): {proc.stderr[-3000:]}")


def duration(path: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True, check=True)
    return float(p.stdout.strip())


def render(item: dict, output: Path, art: Path) -> Path:
    source = Path(item["source"])
    if not source.is_file():
        raise ValueError(f"Source missing: {source}")
    if item.get("ranges"):
        parts = []
        for i, (begin, finish) in enumerate(item["ranges"]):
            begin, finish = float(begin), float(finish)
            if not (0 <= begin < finish <= duration(source)):
                raise ValueError(f"Invalid source range for {item['label']}")
            part = art / f"rank_{item['rank']}_part_{i}.mp4"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                 "-ss", str(begin), "-t", str(finish - begin), "-i", str(source),
                 "-map", "0:v:0", "-map", "0:a:0", "-r", "24", "-c:v", "libx264",
                 "-preset", "ultrafast", "-crf", "20", "-c:a", "aac", "-b:a", "128k",
                 "-ar", "48000", "-ac", "2", str(part)])
            parts.append(part)
        listing = art / f"rank_{item['rank']}_parts.txt"
        listing.write_text("".join("file '" + str(p.resolve()).replace("\\", "/") + "'\n"
                                   for p in parts), encoding="utf-8")
        staged = art / f"rank_{item['rank']}_montage.mp4"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
             "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(staged)])
        source = staged
        start, end = 0.0, duration(source)
    else:
        start, end = float(item["start"]), float(item["end"])
    span = end - start
    if not source.is_file() or not (15 <= span <= 20) or not math.isfinite(span):
        raise ValueError(f"Missing input or invalid 15–20 second selection: {item['label']}")
    if end > duration(source):
        raise ValueError(f"Selection exceeds source: {item['label']}")
    overlay = art / f"rank_{item['rank']}.png"
    make_overlay(overlay, item)
    dest = output / f"{item['rank']}_{item['file_tag']}.mp4"
    vf = ("[0:v]fps=24,split=2[b][f];"
          "[b]scale=360:640:force_original_aspect_ratio=increase,"
          "crop=360:640,boxblur=18:2,scale=720:1280[bg];"
          "[f]scale=720:406,setsar=1[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[base];"
          "[base][1:v]overlay=0:0:shortest=1,format=yuv420p,"
          f"fade=t=in:st=0:d=0.18,fade=t=out:st={span-.24:.3f}:d=0.24[v]")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-ss", str(start), "-t", str(span), "-i", str(source),
         "-loop", "1", "-i", str(overlay), "-filter_complex", vf,
         "-map", "[v]", "-map", "0:a:0", "-af",
         f"afade=t=in:st=0:d=0.12,afade=t=out:st={span-.23:.3f}:d=0.23",
         "-t", str(span), "-r", "24", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "24", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
         "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(dest)])
    actual = duration(dest)
    if abs(actual - span) > .65:
        raise RuntimeError(f"Render duration mismatch: {dest} ({actual:.2f})")
    print(f"Rendered #{item['rank']}: {dest} ({actual:.1f}s)", flush=True)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--allow-missing", action="store_true")
    args = ap.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    clips = plan["clips"]
    if len(clips) != 5 or {c["rank"] for c in clips} != {1, 2, 3, 4, 5}:
        raise ValueError("Plan must define exactly the five unique countdown positions")
    ordered = sorted(clips, key=lambda c: -c["rank"])
    incomplete = [c for c in ordered if c.get("start") is None or not Path(c["source"]).is_file()]
    if incomplete and not args.allow_missing:
        raise ValueError("Missing source or timestamps: " + ", ".join(c["label"] for c in incomplete))
    available = [c for c in ordered if c not in incomplete]
    args.output.mkdir(parents=True, exist_ok=True)
    art = args.output / "_art"
    art.mkdir(exist_ok=True)
    result = [render(c, args.output, art) for c in available]
    intro = art / "intro.png"
    make_intro(intro, complete=not incomplete)
    intro_video = art / "intro.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-loop", "1", "-framerate", "24", "-i", str(intro),
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2.2",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
         "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "aac", "-ar", "48000",
         "-ac", "2", "-movflags", "+faststart", str(intro_video)])
    concat = art / "concat.txt"
    concat.write_text("".join("file '" + str(p.resolve()).replace("\\", "/") + "'\n"
                              for p in [intro_video, *result]), encoding="utf-8")
    final = args.output / ("Top_5_Peter_Getting_Harassed.mp4" if not incomplete
                           else "DRAFT_Peter_Moments.mp4")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy",
         "-movflags", "+faststart", str(final)])
    manifest = {"final": str(final), "complete": not incomplete,
                "clips": [{"rank": c["rank"], "file": str(p),
                           "seconds": round(duration(p), 2)} for c,p in zip(available, result)],
                "pending": [c["label"] for c in incomplete],
                "publication": "manual_review_only"}
    (args.output / "render_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Compilation: {final} ({duration(final):.1f}s) | complete={not incomplete}", flush=True)


if __name__ == "__main__":
    main()
