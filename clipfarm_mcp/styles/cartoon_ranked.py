"""Opt-in ranked-cartoon video renderer. Does not modify ClipFarm's legacy renderer.

Usage: python -m clipfarm_mcp.styles.cartoon_ranked PLAN.json --output DIR
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

PRESET = Path(__file__).parent / "presets" / "cartoon_ranked_v1.json"
FONT = Path("C:/Windows/Fonts/arialbi.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/arialbd.ttf")


def call(cmd: list[str], *, cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, errors="replace")
    if proc.returncode:
        raise RuntimeError(f"Command failed ({proc.returncode}): {proc.stderr[-4000:]}")


def probe(path: Path) -> dict:
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-show_entries", "stream=codec_type,width,height",
                           "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def length(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def validate_plan(plan: dict, preset: dict) -> list[dict]:
    if plan.get("style_id") != preset["style_id"]:
        raise ValueError("Select this style explicitly by style_id")
    clips = plan.get("clips", [])
    if len(clips) != 5 or {c.get("rank") for c in clips} != {1, 2, 3, 4, 5}:
        raise ValueError("This preset requires five uniquely numbered clips")
    for c in clips:
        source = Path(c["source"])
        if not source.is_file():
            raise ValueError(f"Missing source: {source}")
        spans = c.get("ranges", [])
        if not spans:
            raise ValueError(f"No source intervals for #{c['rank']}")
        total = 0.0
        duration = length(source)
        for start, end in spans:
            if not all(math.isfinite(float(v)) for v in (start, end)):
                raise ValueError("Timestamps must be finite")
            if not (0 <= float(start) < float(end) <= duration):
                raise ValueError(f"Invalid source interval for #{c['rank']}")
            total += end - start
        if not (preset["minimum_clip_seconds"] <= total <= preset["maximum_clip_seconds"]):
            raise ValueError(f"Clip #{c['rank']} must be 25–30 seconds (got {total:.1f})")
    return sorted(clips, key=lambda c: -c["rank"])


def episode_clip(item: dict, art: Path, fps: int) -> Path:
    """Extract source intervals once. The hypnosis item combines setup and payoff."""
    parts = []
    for i, (start, end) in enumerate(item["ranges"]):
        part = art / f"{item['rank']}_source_{i}.mp4"
        call(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
              "-ss", str(start), "-i", item["source"], "-t", str(end-start),
              "-map", "0:v:0", "-map", "0:a:0", "-r", str(fps),
              "-vf", "scale=852:480,setsar=1", "-c:v", "libx264", "-crf", "22",
              "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac",
              "-ar", "48000", "-ac", "2", "-b:a", "128k", str(part)])
        parts.append(part)
    if len(parts) == 1:
        return parts[0]
    listfile = art / f"{item['rank']}_join.txt"
    listfile.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts),
                        encoding="utf-8")
    joined = art / f"{item['rank']}_source_joined.mp4"
    call(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
          "-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(joined)])
    return joined


def font(sz: int, italic: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT if italic else FONT_BOLD), sz)


def outlined(draw: ImageDraw.ImageDraw, pos: tuple[int, int], text: str,
             f: ImageFont.FreeTypeFont, fill: str = "#FFFFFF", sw: int = 3) -> None:
    draw.text((pos[0] + 2, pos[1] + 3), text, font=f, fill="#151515", stroke_width=sw+1,
              stroke_fill="#151515")
    draw.text(pos, text, font=f, fill=fill, stroke_width=sw, stroke_fill="#161616")


def stylized_line(draw: ImageDraw.ImageDraw, x: int, y: int,
                  parts: list[tuple[str, str]], limit: int = 670) -> None:
    size = 39
    while size > 24:
        f = font(size)
        if sum(draw.textbbox((0, 0), t, font=f)[2] for t, _ in parts) <= limit:
            break
        size -= 1
    for text, col in parts:
        outlined(draw, (x, y), text, f, col, sw=3)
        x += draw.textbbox((0, 0), text, font=f)[2]


def frame_at(source: Path, seconds: float) -> Image.Image:
    cap = cv2.VideoCapture(str(source))
    cap.set(cv2.CAP_PROP_POS_MSEC, seconds*1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"Cannot preview scene: {source.name} at {seconds}")
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def create_backplate(item: dict, preset: dict, art: Path) -> Path:
    w, h = preset["width"], preset["height"]
    start = float(item["ranges"][0][0]) + .7
    source_frame = frame_at(Path(item["source"]), start)
    full = ImageOps.fit(source_frame, (w, h), method=Image.Resampling.BICUBIC)
    full = full.filter(ImageFilter.GaussianBlur(48)).convert("RGBA")
    pastel = ["#F6BD9B", "#9CCAD4", "#C8E5DA", "#D7D9ED", "#B3DDD4"][5-item["rank"]]
    wash = Image.new("RGBA", (w, h), pastel)
    full = Image.blend(full, wash, .66)
    d = ImageDraw.Draw(full, "RGBA")
    d.rectangle((0, 0, w, 321), fill=(239, 243, 235, 56))
    d.rectangle((0, 315, w, 324), fill=(12, 21, 22, 190))
    d.rectangle((0, 1102, w, 1110), fill=(12, 21, 22, 175))
    # The list is anchored on the LEFT, as in the reference channel.
    stylized_line(d, 24, 20, [("RANKING ", "#FFFFFF"), ("TOP 5 ", "#FF9839"),
                                ("TIMES ", "#FFFFFF"), ("PETER", "#FF9839")])
    stylized_line(d, 24, 72, [("GOT ", "#FFFFFF"), ("HARASSED", "#5CE17C")])
    for rank in range(1, 6):
        y = preset["first_row_y"] + (rank - 1) * preset["row_spacing"]
        revealed = rank >= item["rank"]
        selected = rank == item["rank"]
        if selected:
            d.rounded_rectangle((27, y-2, 689, y+33), radius=8, fill=(12, 17, 20, 97))
        f = font(28, italic=False)
        colour = "#FFD63B" if selected else "#F8FCFF"
        label = preset["labels"][str(rank)] if revealed else ""
        outlined(d, (preset["list_x"], y), f"{rank}. {label}", f, colour, sw=2)
    # Lower edge is intentionally clean: no imitation of FuryBeez watermark.
    output = art / f"{item['rank']}_backplate.png"
    full.convert("RGB").save(output)
    return output


def whoosh(path: Path, seconds: float = .36) -> Path:
    """Create an original quiet swish, not a sample copied from another video."""
    if path.exists():
        return path
    rng = np.random.default_rng(20260924)
    sample_rate = 48000
    n = int(sample_rate * seconds)
    t = np.arange(n) / sample_rate
    noise = rng.normal(0, 1, n)
    smooth = np.convolve(noise, np.ones(14)/14, mode="same")
    transient = noise - np.convolve(noise, np.ones(65)/65, mode="same")
    phase = 2 * np.pi * (190 * t + 1700 * t*t)
    amp = (1 - np.exp(-t*65)) * np.exp(-t*12)
    signal = (0.7 * transient + .5 * smooth + .22 * np.sin(phase)) * amp
    signal *= .4 / max(1e-6, np.max(np.abs(signal)))
    pcm = (np.clip(signal, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return path


def ass_time(seconds: float) -> str:
    n = int(max(0, seconds) * 100)
    return f"{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}"


def ass_caption_file(source: Path, dest: Path, *, model) -> None:
    """Word-timed, short captions, generated only from the selected source clip."""
    segs, _ = model.transcribe(str(source), word_timestamps=True, vad_filter=True)
    words = []
    for segment in segs:
        for w in segment.words or []:
            if w.word.strip():
                words.append((float(w.start), max(float(w.end), float(w.start) + .1), w.word.strip()))
    script = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 720", "PlayResY: 1280", "WrapStyle: 2",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Dialogue,Arial,43,&H00FFFFFF,&H00FFFFFF,&H00121212,&H60000000,-1,0,0,0,100,100,0,0,1,3,1,2,32,32,237,1",
        "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    buffer = []
    for start, end, word in words:
        if buffer and (start-buffer[-1][1] > .27 or end-buffer[0][0] > 1.2
                       or sum(len(w[2]) for w in buffer) + len(word) > 16):
            phrase = " ".join(w[2] for w in buffer).replace("{", "(").replace("}", ")")
            script.append(f"Dialogue: 0,{ass_time(buffer[0][0])},{ass_time(buffer[-1][1])},Dialogue,,0,0,0,,{phrase}")
            buffer = []
        buffer.append((start, end, word))
    if buffer:
        phrase = " ".join(w[2] for w in buffer).replace("{", "(").replace("}", ")")
        script.append(f"Dialogue: 0,{ass_time(buffer[0][0])},{ass_time(buffer[-1][1])},Dialogue,,0,0,0,,{phrase}")
    dest.write_text("\n".join(script)+"\n", encoding="utf-8-sig")
    print(f"Caption groups for {source.name}: {len(script)-10}", flush=True)


def render(item: dict, src: Path, backdrop: Path, subtitles: Path, swish: Path,
           dest: Path, art: Path, preset: dict) -> dict:
    seconds = length(src)
    if not (24.5 <= seconds <= 30.5):
        raise ValueError(f"Expected 25–30s scene, actual {seconds:.2f}s for #{item['rank']}")
    vf = (f"[0:v]fps={preset['fps']},scale=720:780:force_original_aspect_ratio=increase,"
          "crop=720:780,setsar=1[scene];[1:v]format=yuv420p[back];"
          "[back][scene]overlay=0:322:shortest=1,format=yuv420p,"
          f"ass=filename={subtitles.name}[v]")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(src), "-loop", "1", "-framerate", str(preset["fps"]),
           "-i", str(backdrop)]
    if item["rank"] < 5:
        cmd += ["-i", str(swish)]
        vf += (";[0:a]aresample=48000,volume=1.0[dialogue];"
               f"[2:a]aresample=48000,volume={preset['transition']['gain']}[sfx];"
               "[dialogue][sfx]amix=inputs=2:duration=first:normalize=0,"
               "alimiter=limit=0.95[a]")
        audio_map = "[a]"
    else:
        audio_map = "0:a:0"
    cmd += ["-filter_complex", vf, "-map", "[v]", "-map", audio_map,
            "-t", str(seconds), "-r", str(preset["fps"]), "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(dest)]
    call(cmd, cwd=art)
    actual = length(dest)
    if not 24.5 <= actual <= 30.5:
        raise RuntimeError(f"Rendered clip violates 25–30 second limit: {dest}: {actual}")
    return {"rank": item["rank"], "duration": round(actual, 2), "source": str(src),
            "file": str(dest), "ranges": item["ranges"],
            "aftermath_note": item.get("aftermath_note", ""),
            "transition_whoosh": item["rank"] < 5}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--whisper-model", default="base", choices=["tiny", "base", "small"])
    args = ap.parse_args()
    preset = json.loads(PRESET.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    ordered = validate_plan(plan, preset)
    args.output.mkdir(parents=True, exist_ok=True)
    art = args.output / "_style_assets"
    art.mkdir(exist_ok=True)
    (art / "preset_snapshot.json").write_text(json.dumps(preset, indent=2), encoding="utf-8")
    original_whoosh = whoosh(art / "original_whoosh.wav", preset["transition"]["duration_seconds"])
    from faster_whisper import WhisperModel
    model = WhisperModel(args.whisper_model, device="cpu", compute_type="int8")
    completed = []
    for item in ordered:
        src = episode_clip(item, art, preset["fps"])
        bg = create_backplate(item, preset, art)
        ass = art / f"rank_{item['rank']}.ass"
        ass_caption_file(src, ass, model=model)
        final_scene = args.output / f"{item['rank']}_{item['file_tag']}_ranked.mp4"
        meta = render(item, src, bg, ass, original_whoosh, final_scene, art, preset)
        completed.append(meta)
        print(f"Rendered #{item['rank']} ({meta['duration']} seconds)", flush=True)
    concat = art / "join_final.txt"
    concat.write_text("".join(f"file '{Path(m['file']).resolve().as_posix()}'\n" for m in completed),
                      encoding="utf-8")
    final = args.output / "Top_5_Peter_Cartoon_Ranked_25-30s.mp4"
    call(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
          "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy",
          "-movflags", "+faststart", str(final)])
    manifest = {"style_id": preset["style_id"], "intro_seconds": 0,
                "rendered": completed, "final": str(final), "total_duration": round(length(final), 2),
                "source_plan": str(args.plan), "publication": "manual_review_only"}
    (args.output / "render_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"FINAL: {final} | {manifest['total_duration']}s", flush=True)


if __name__ == "__main__":
    main()
