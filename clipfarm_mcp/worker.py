"""Durable local preparation/render subprocess; never accesses a model API."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from clipfarm_mcp import core


def _status(directory: Path, phase: str, **extras) -> None:
    core._atomic(directory / "status.json", {"phase": phase, "updated_at": core._now(), **extras})


def _probe(path: Path) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        capture_output=True, text=True, timeout=35, check=True,
    )
    duration = float(p.stdout.strip())
    max_hours = float(os.environ.get("CLIPFARM_MAX_DURATION_HOURS", "4"))
    if not 0 < duration <= max_hours * 3600:
        raise ValueError("source duration outside allowed range")
    if path.stat().st_size > core.MAX_SOURCE_BYTES:
        raise ValueError("source exceeds configured size limit")
    return duration


def _fetch_source(directory: Path, manifest: dict) -> tuple[Path, str]:
    if manifest.get("source_path"):
        source = core._allowed_local(manifest["source_path"])
        target = directory / ("source" + source.suffix.lower())
        if target.resolve() != source:
            if shutil.disk_usage(directory).free < source.stat().st_size + 512 * 1024**2:
                raise ValueError("insufficient free disk to copy source")
            shutil.copyfile(source, target)
        return target, source.stem
    url = manifest.get("url", "")
    if not core._allowed_url(url):
        raise ValueError("source URL is no longer permitted")
    from yt_dlp import YoutubeDL

    opts = {"outtmpl": str(directory / "source.%(ext)s"), "format": "bv*+ba/b",
            "merge_output_format": "mp4", "noplaylist": True, "quiet": True,
            "max_filesize": core.MAX_SOURCE_BYTES, "ignoreerrors": False,
            "restrictfilenames": True}
    with YoutubeDL(opts) as downloader:
        info = downloader.extract_info(url, download=True)
    if not info or info.get("_type") == "playlist":
        raise ValueError("expected a single video source")
    videos = [p for p in directory.glob("source.*") if p.suffix.lower() in core.ALLOWED_SUFFIXES]
    if len(videos) != 1 or videos[0].resolve().parent != directory.resolve():
        raise ValueError("could not uniquely resolve downloaded video")
    return videos[0], str(info.get("title") or "source")[:200]


def prepare(directory: Path) -> None:
    manifest = core._read(directory / "manifest.json")
    source, title = _fetch_source(directory, manifest)
    duration = _probe(source)
    manifest.update(source_filename=source.name, title=title, duration=duration)
    core._atomic(directory / "manifest.json", manifest)
    _status(directory, "transcribing", title=title, duration=duration)
    from faster_whisper import WhisperModel

    model_name = os.environ.get("CLIPFARM_WHISPER_MODEL", "small")
    if model_name not in {"tiny", "base", "small", "medium", "large-v3", "distil-large-v3"}:
        raise ValueError("unsupported local Whisper model")
    model = WhisperModel(model_name, device="auto", compute_type="int8")
    segments, info = model.transcribe(str(source), word_timestamps=True, vad_filter=True)
    parsed = []
    for segment in segments:
        words = [{"word": w.word, "start": float(w.start), "end": float(w.end),
                  "probability": float(w.probability or 0)} for w in (segment.words or [])]
        parsed.append({"text": segment.text, "start": float(segment.start),
                       "end": float(segment.end), "words": words})
    transcript = {"text": " ".join(s["text"].strip() for s in parsed),
                  "segments": parsed, "language": info.language}
    core._atomic(directory / "transcript.json", transcript)
    core.load_transcript_file(str(directory / "transcript.json"))
    _status(directory, "awaiting_selection", title=title, duration=duration,
            total_words=sum(len(s["words"]) for s in parsed))


def render(directory: Path) -> None:
    manifest = core._read(directory / "manifest.json")
    filename = manifest.get("source_filename", "")
    source = directory / filename
    if not filename or source.resolve().parent != directory.resolve() or not source.is_file():
        raise ValueError("source is unavailable")
    transcript = core.load_transcript_file(str(directory / "transcript.json"))
    payload = core._read(directory / "highlights.json")
    core.validate_selection(payload, transcript, float(manifest["duration"]))
    out = directory / "render"
    out.mkdir(exist_ok=True)
    env = os.environ.copy()
    for key in ("GEMINI_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "ZERNIO_API_KEY"):
        env.pop(key, None)
    env["TRANSCRIPTION_PROVIDER"] = "whisper"
    env["PYTHONPATH"] = os.pathsep.join([str(core.REPO / "src"), str(core.REPO), env.get("PYTHONPATH", "")])
    argv = [sys.executable, "-u", "-m", "clippyme.pipeline.orchestrator",
            "--input", str(source), "--output", str(out),
            "--transcript-file", str(directory / "transcript.json"),
            "--highlights-file", str(directory / "highlights.json"),
            "--reframe-mode", manifest.get("reframe_mode", "auto")]
    print("Executing local renderer with externally supplied highlights", flush=True)
    completed = subprocess.run(argv, cwd=str(core.REPO), env=env, check=False)
    if completed.returncode:
        raise RuntimeError(f"renderer exited with status {completed.returncode}; inspect render.log")
    clips = core.list_clips(directory.name)
    if not clips:
        raise RuntimeError("renderer completed but no verified clips were available")
    _status(directory, "ready_for_review", count=len(clips))


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in {"prepare", "render"}:
        raise SystemExit("Usage: python -m clipfarm_mcp.worker prepare|render <job_id>")
    operation, job_id = sys.argv[1:]
    directory = core.job_dir(job_id)
    try:
        (prepare if operation == "prepare" else render)(directory)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        _status(directory, "failed", operation=operation, error=str(exc)[:400])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
