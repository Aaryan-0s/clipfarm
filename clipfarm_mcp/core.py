"""Host-testable ClipFarm job and approval state; no AI or browser automation."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from clippyme.pipeline.external_highlights import (
    load_transcript_file, validate_selection,
)

REPO = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("CLIPFARM_DATA_DIR", str(REPO / "data" / "clipfarm"))).resolve()
IMPORT_ROOT = Path(os.environ.get("CLIPFARM_IMPORT_ROOT", str(DATA_ROOT / "imports"))).resolve()
ALLOWED_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
                 "www.twitch.tv", "twitch.tv", "kick.com", "www.kick.com"}
JOB_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
MAX_SOURCE_BYTES = int(os.getenv("CLIPFARM_MAX_SOURCE_GB", "8")) * 1024**3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".clipfarm-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as fp:
        obj = json.load(fp)
    if not isinstance(obj, dict):
        raise ValueError("invalid job metadata")
    return obj


def job_dir(job_id: str) -> Path:
    if not isinstance(job_id, str) or not JOB_RE.fullmatch(job_id):
        raise ValueError("invalid ClipFarm job ID")
    target = (DATA_ROOT / "jobs" / job_id).resolve()
    if target.parent != (DATA_ROOT / "jobs").resolve() or not target.is_dir():
        raise ValueError("ClipFarm job not found")
    return target


def _allowed_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname in ALLOWED_HOSTS
                and not parts.username and not parts.password and (parts.port in (None, 443)))
    except ValueError:
        return False


def _allowed_local(source_path: str) -> Path:
    source = Path(source_path).resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("source must be a supported video file")
    if source != IMPORT_ROOT and IMPORT_ROOT not in source.parents:
        raise ValueError(f"local source must be inside the approved import directory: {IMPORT_ROOT}")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("source exceeds configured size limit")
    return source


def _spawn(job_id: str, operation: str) -> int:
    # Explicit argv; no shell, inherited API keys removed to ensure this
    # handoff cannot accidentally spend external inference/publishing credits.
    env = os.environ.copy()
    for key in ("GEMINI_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "ZERNIO_API_KEY"):
        env.pop(key, None)
    env["TRANSCRIPTION_PROVIDER"] = "whisper"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "src"), str(REPO), env.get("PYTHONPATH", "")])
    directory = job_dir(job_id)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with (directory / f"{operation}.log").open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "clipfarm_mcp.worker", operation, job_id],
            cwd=str(REPO), env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
        )
    return process.pid


def prepare_video(*, source_path: str = "", url: str = "", rights_confirmed: bool = False,
                  reframe_mode: str = "disabled") -> dict:
    if bool(source_path) == bool(url):
        raise ValueError("supply exactly one local source_path or URL")
    if not rights_confirmed:
        raise ValueError("confirm you own or are authorized to clip this source")
    if reframe_mode not in {"auto", "disabled", "subject"}:
        raise ValueError("invalid reframe mode")
    if url and not _allowed_url(url):
        raise ValueError("only HTTPS YouTube, Twitch and Kick source URLs are supported")
    local_source = str(_allowed_local(source_path)) if source_path else ""
    directory = DATA_ROOT / "jobs" / str(uuid.uuid4())
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"id": directory.name, "url": url, "source_path": local_source,
                "rights_confirmed": True, "reframe_mode": reframe_mode, "created_at": _now()}
    _atomic(directory / "manifest.json", manifest)
    _atomic(directory / "status.json", {"phase": "preparing", "updated_at": _now()})
    pid = _spawn(directory.name, "prepare")
    return {"job_id": directory.name, "phase": "preparing", "pid": pid,
            "next": "Use get_job_status, then get_transcript when the phase is awaiting_selection."}


def get_job_status(job_id: str) -> dict:
    directory = job_dir(job_id)
    status = _read(directory / "status.json")
    status["job_id"] = job_id
    runtime = directory / "render" / ".clippyme_runtime.json"
    if runtime.is_file():
        try:
            progress = _read(runtime)
            status["render_runtime"] = {k: progress.get(k) for k in ("phase", "progress", "status", "detail")}
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return status


def list_pending(limit: int = 25) -> list[dict]:
    root = DATA_ROOT / "jobs"
    if not root.exists():
        return []
    pending = []
    for directory in sorted(root.iterdir(), reverse=True):
        if not directory.is_dir() or not JOB_RE.fullmatch(directory.name):
            continue
        try:
            status = _read(directory / "status.json")
            if status.get("phase") in {"awaiting_selection", "selected", "ready_for_review", "failed"}:
                manifest = _read(directory / "manifest.json")
                pending.append({"job_id": directory.name, "phase": status["phase"],
                                "title": manifest.get("title") or directory.name,
                                "duration": manifest.get("duration")})
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if len(pending) >= max(1, min(limit, 100)):
            break
    return pending


def get_transcript(job_id: str, offset: int = 0, limit: int = 250) -> dict:
    directory = job_dir(job_id)
    transcript = load_transcript_file(str(directory / "transcript.json"))
    words = [{"word": w["word"], "start": w["start"], "end": w["end"],
              **({"speaker": w["speaker"]} if "speaker" in w else {})}
             for segment in transcript["segments"] for w in segment["words"]]
    offset, limit = max(0, int(offset)), max(1, min(int(limit), 500))
    manifest = _read(directory / "manifest.json")
    return {"job_id": job_id, "title": manifest.get("title"),
            "duration": manifest.get("duration"), "total_words": len(words),
            "offset": offset, "next_offset": offset + limit if offset + limit < len(words) else None,
            "words": words[offset:offset + limit],
            "instructions": "Select 10–75 second complete moments. Return start/end seconds and fields matching the clip selection contract; estimates are not guaranteed virality."}


def submit_highlights(job_id: str, shorts: list[dict]) -> dict:
    directory = job_dir(job_id)
    if get_job_status(job_id)["phase"] != "awaiting_selection":
        raise ValueError("job is not awaiting a selection, or is already rendering")
    manifest = _read(directory / "manifest.json")
    transcript = load_transcript_file(str(directory / "transcript.json"))
    selection = validate_selection({"shorts": shorts}, transcript, float(manifest["duration"]))
    _atomic(directory / "highlights.json", selection)
    _atomic(directory / "status.json", {"phase": "selected", "updated_at": _now(),
                                        "count": len(selection["shorts"])})
    return {"job_id": job_id, "count": len(selection["shorts"]), "phase": "selected",
            "next": "Call render_job, then inspect clips and approve them."}


def render_job(job_id: str) -> dict:
    directory = job_dir(job_id)
    if get_job_status(job_id)["phase"] != "selected":
        raise ValueError("submit and validate a selection before rendering")
    if not (directory / "highlights.json").is_file():
        raise ValueError("highlights file missing")
    _atomic(directory / "status.json", {"phase": "rendering", "updated_at": _now()})
    try:
        pid = _spawn(job_id, "render")
    except Exception:
        _atomic(directory / "status.json", {"phase": "selected", "updated_at": _now()})
        raise
    return {"job_id": job_id, "phase": "rendering", "pid": pid}


def list_clips(job_id: str) -> list[dict]:
    directory = job_dir(job_id)
    result_dir = directory / "render"
    if not result_dir.is_dir():
        return []
    metas = sorted(result_dir.glob("*_metadata.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not metas:
        return []
    result = []
    for i, item in enumerate(_read(metas[0]).get("shorts", [])):
        filename = item.get("clip_filename") or ""
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".mp4"):
            continue
        clip = result_dir / filename
        if clip.is_file() and clip.stat().st_size:
            result.append({"index": i, "title": item.get("video_title_for_youtube_short"),
                           "hook": item.get("viral_hook_text"), "start": item.get("start"),
                           "end": item.get("end"), "file": str(clip),
                           "qa": item.get("qa")})
    return result


def approve_clips(job_id: str, clip_indices: list[int]) -> dict:
    directory = job_dir(job_id)
    if get_job_status(job_id)["phase"] not in {"ready_for_review", "approved"}:
        raise ValueError("render must finish before approval")
    available = {entry["index"] for entry in list_clips(job_id)}
    requested = set(clip_indices)
    if not requested or not requested.issubset(available):
        raise ValueError("approval contains an unavailable clip index")
    _atomic(directory / "approval.json", {"approved_indices": sorted(requested),
                                          "approved_at": _now(), "publishing": "manual_only"})
    _atomic(directory / "status.json", {"phase": "approved", "updated_at": _now(),
                                        "approved_count": len(requested)})
    return {"job_id": job_id, "approved_indices": sorted(requested),
            "publishing": "manual_only", "note": "No social account was accessed or posted to."}


def get_frame(job_id: str, seconds: float, clip_index: int | None = None) -> bytes:
    directory = job_dir(job_id)
    manifest = _read(directory / "manifest.json")
    if clip_index is None:
        video = directory / manifest.get("source_filename", "source.mp4")
        upper = float(manifest.get("duration") or 0)
    else:
        found = next((c for c in list_clips(job_id) if c["index"] == clip_index), None)
        if not found:
            raise ValueError("clip not found")
        video = Path(found["file"])
        upper = float(found["end"]) - float(found["start"])
    if not isinstance(seconds, (float, int)) or not (0 <= seconds <= upper):
        raise ValueError("frame time is outside video duration")
    output = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(seconds),
                             "-i", str(video), "-frames:v", "1", "-vf", "scale=640:-2",
                             "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                            capture_output=True, timeout=30, check=True)
    if not output.stdout or len(output.stdout) > 2_000_000:
        raise ValueError("no bounded image frame available")
    return output.stdout
