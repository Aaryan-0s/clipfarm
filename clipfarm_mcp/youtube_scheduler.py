"""Opt-in, human-approved YouTube scheduling for finished local ClipFarm videos.

No network action happens during import, draft creation or approval. Only the
explicit ``schedule`` CLI action can upload. YouTube itself handles the future
publish time; no persistent ClipFarm daemon is required.

An unverified YouTube Data API project may be locked to private uploads. A
successful upload is NOT proof that YouTube will publish it; verify in Studio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clipfarm_mcp import core

BASE = core.DATA_ROOT / "youtube_scheduler"
CREDS_DIR = BASE / "credentials"
TOKEN = CREDS_DIR / "youtube_token.json"
CLIENT = CREDS_DIR / "oauth_desktop_client.json"
QUEUE = BASE / "queue"
SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
)
ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
CHANNEL_PATTERN = re.compile(r"^UC[-_A-Za-z0-9]{22}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat(timespec="seconds")


def _atomic_write(path: Path, obj: dict) -> None:
    """Durable queue journal; keep tokens outside version control."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".youtube-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _safe_record_path(record_id: str, queue_dir: Path = QUEUE) -> Path:
    if not ID_PATTERN.fullmatch(record_id):
        raise ValueError("Invalid schedule draft ID")
    return queue_dir / f"{record_id}.json"


def _record(record_id: str, queue_dir: Path = QUEUE) -> dict:
    path = _safe_record_path(record_id, queue_dir)
    if not path.is_file():
        raise FileNotFoundError("Schedule draft not found")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("id") != record_id:
        raise ValueError("Queue record identity mismatch")
    return obj


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _snapshot(path: Path) -> dict:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.stat().st_size:
        raise ValueError(f"Not a usable file: {path}")
    return {"path": str(resolved), "bytes": resolved.stat().st_size,
            "sha256": _hash_file(resolved)}


def _check_snapshot(file_info: dict) -> Path:
    path = Path(file_info["path"]).resolve(strict=True)
    if path.stat().st_size != file_info["bytes"] or _hash_file(path) != file_info["sha256"]:
        raise ValueError(f"Reviewed file changed since approval: {path}")
    return path


def _publish_datetime(value: str, *, now: datetime | None = None) -> str:
    """Require timezone and future; never let a past publishAt publish now."""
    try:
        date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("Enter an ISO 8601 date/time with timezone, e.g. 2026-10-02T18:00:00+05:45") from exc
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError("Publishing time must have a timezone offset")
    moment = date.astimezone(timezone.utc)
    if moment <= (now or _now()) + timedelta(minutes=45):
        raise ValueError("Schedule at least 45 minutes in the future; past times publish immediately")
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def prepare(folder: str | Path, *, title: str = "", description: str = "",
            queue_dir: Path = QUEUE) -> dict:
    """Snapshot the final MP4 and thumbnail, without approving or uploading."""
    parent = Path(folder).resolve(strict=True)
    manifest_path = parent / "render_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Folder needs a render_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    video = Path(manifest["final"]).resolve(strict=True)
    if video.parent != parent or video.suffix.lower() != ".mp4":
        raise ValueError("Manifest final MP4 must be directly inside the selected render folder")
    thumbnail = Path(manifest.get("thumbnail") or parent / "thumbnail_1280x720.png").resolve(strict=True)
    if thumbnail.parent != parent or thumbnail.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Thumbnail must be a JPG/PNG directly inside the selected render folder")
    suggested_title = str(title or manifest.get("title") or "").strip()
    if not suggested_title or len(suggested_title) > 100:
        raise ValueError("Supply an explicit YouTube title of 1–100 characters")
    description = description.strip()
    if len(description) > 5000:
        raise ValueError("Description exceeds YouTube's 5000-character limit")
    video_snapshot = _snapshot(video)
    thumbnail_snapshot = _snapshot(thumbnail)
    for existing in list_queue(queue_dir):
        if (existing["video"]["path"] == video_snapshot["path"] and
                existing["video"]["sha256"] == video_snapshot["sha256"]):
            if (existing["state"] == "awaiting_review" and
                    existing["thumbnail"]["sha256"] == thumbnail_snapshot["sha256"] and
                    existing["metadata"]["title"] == suggested_title and
                    existing["metadata"]["description"] == description):
                return existing
            raise ValueError("This exact video already has a YouTube draft/upload. "
                             "Review the existing queue entry; never create a duplicate upload.")
    record_id = uuid.uuid4().hex
    record = {
        "id": record_id, "state": "awaiting_review", "created_at": _iso_now(),
        "render_folder": str(parent), "render_manifest_sha256": _hash_file(manifest_path),
        "video": video_snapshot, "thumbnail": thumbnail_snapshot,
        "metadata": {"title": suggested_title, "description": description, "tags": [],
                     "category_id": "24"},  # entertainment
        "approval": None, "youtube": None,
    }
    _atomic_write(_safe_record_path(record_id, queue_dir), record)
    return record


def approve(record_id: str, *, channel_id: str, publish_at: str,
            made_for_kids: bool, queue_dir: Path = QUEUE) -> dict:
    """Human approval locks the exact files, metadata, channel and publish time."""
    record = _record(record_id, queue_dir)
    if record["state"] not in {"awaiting_review", "approved"}:
        raise ValueError("This upload is already in progress or finalized; cannot reapprove")
    if not CHANNEL_PATTERN.fullmatch(channel_id):
        raise ValueError("Enter the exact UC... channel ID, not a display name or handle")
    pub = _publish_datetime(publish_at)
    _check_snapshot(record["video"])
    _check_snapshot(record["thumbnail"])
    record["approval"] = {
        "channel_id": channel_id, "publish_at_utc": pub,
        "made_for_kids": bool(made_for_kids),
        "video_sha256": record["video"]["sha256"],
        "thumbnail_sha256": record["thumbnail"]["sha256"],
        "metadata_sha256": hashlib.sha256(json.dumps(record["metadata"], sort_keys=True)
                                          .encode("utf-8")).hexdigest().upper(),
        "approved_at": _iso_now(),
    }
    record["state"] = "approved"
    _atomic_write(_safe_record_path(record_id, queue_dir), record)
    return record


def list_queue(queue_dir: Path = QUEUE) -> list[dict]:
    if not queue_dir.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(queue_dir.glob("*.json")) if ID_PATTERN.fullmatch(p.stem)]


def oauth_connect(client_json: Path = CLIENT, token_json: Path = TOKEN) -> list[dict]:
    """User personally completes Google's browser sign-in; never share passwords."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    source = client_json.resolve(strict=True)
    info = json.loads(source.read_text(encoding="utf-8"))
    if "installed" not in info:
        raise ValueError("Google OAuth credentials must be a Desktop application client JSON")
    flow = InstalledAppFlow.from_client_secrets_file(str(source), SCOPES)
    creds = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True,
                                  access_type="offline", prompt="consent")
    _atomic_write(token_json, json.loads(creds.to_json()))
    return owned_channels(_youtube(creds))


def _youtube(creds):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def authenticated_service(token_json: Path = TOKEN):
    if not token_json.is_file():
        raise FileNotFoundError("Channel is not connected: run 'connect' first")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(token_json), scopes=SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _atomic_write(token_json, json.loads(creds.to_json()))
    if not creds.valid:
        raise ValueError("YouTube token needs reconnection; rerun 'connect'")
    return _youtube(creds)


def owned_channels(service) -> list[dict]:
    resp = service.channels().list(part="snippet", mine=True, maxResults=50).execute()
    return [{"channel_id": c["id"], "title": c.get("snippet", {}).get("title", "")}
            for c in resp.get("items", [])]


def _schedule_body(record: dict) -> dict:
    approval = record["approval"]
    if not approval:
        raise ValueError("Review and approve video, thumbnail, channel and time before scheduling")
    return {
        "snippet": {
            "title": record["metadata"]["title"],
            "description": record["metadata"]["description"],
            "categoryId": record["metadata"]["category_id"],
        },
        "status": {"privacyStatus": "private",
                   "publishAt": approval["publish_at_utc"],
                   "selfDeclaredMadeForKids": approval["made_for_kids"]},
    }


def upload_approved(record_id: str, *, confirmation: str, service=None,
                    queue_dir: Path = QUEUE) -> dict:
    """Only network-changing action; journal before upload to avoid silent duplicates."""
    record = _record(record_id, queue_dir)
    if confirmation != f"SCHEDULE {record_id}":
        raise ValueError(f"Final explicit confirmation must equal: SCHEDULE {record_id}")
    if record["state"] != "approved":
        raise ValueError("Already attempted or not approved; never automatically retry an upload")
    for existing in list_queue(queue_dir):
        if (existing["id"] != record_id and
                existing["video"]["sha256"] == record["video"]["sha256"] and
                existing["state"] not in {"awaiting_review"}):
            raise ValueError("Another queue item already approved or uploaded this same video")
    approval = record["approval"]
    _publish_datetime(approval["publish_at_utc"])
    video = _check_snapshot(record["video"])
    thumb = _check_snapshot(record["thumbnail"])
    if approval["video_sha256"] != record["video"]["sha256"] or (
            approval["thumbnail_sha256"] != record["thumbnail"]["sha256"]):
        raise ValueError("Approved files differ from draft; review again")
    metadata_digest = hashlib.sha256(json.dumps(record["metadata"], sort_keys=True)
                                     .encode("utf-8")).hexdigest().upper()
    if approval["metadata_sha256"] != metadata_digest:
        raise ValueError("Approved title/description changed; review again")
    service = service or authenticated_service()
    channels = owned_channels(service)
    if approval["channel_id"] not in {c["channel_id"] for c in channels}:
        raise ValueError("Connected Google account is not the channel approved for upload")

    # A crash after this point may have reached YouTube. Never silently retry:
    # reconcile manually in Studio if the API outcome is unknown.
    record["state"] = "uploading"
    record["upload_started_at"] = _iso_now()
    _atomic_write(_safe_record_path(record_id, queue_dir), record)
    from googleapiclient.http import MediaFileUpload

    body = _schedule_body(record)
    try:
        request = service.videos().insert(part="snippet,status", body=body,
                                          notifySubscribers=False,
                                          media_body=MediaFileUpload(str(video), mimetype="video/mp4",
                                                                     chunksize=8 * 1024 * 1024,
                                                                     resumable=True))
        response = None
        while response is None:
            _progress, response = request.next_chunk()
        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("YouTube returned no video ID; check Studio before retrying")
    except Exception:
        record["state"] = "upload_uncertain"
        record["error_note"] = "Upload may have reached YouTube. Check Studio before retrying."
        _atomic_write(_safe_record_path(record_id, queue_dir), record)
        raise

    # Store the video ID *before* trying the thumbnail or status verification.
    record["youtube"] = {"video_id": video_id,
                         "url": f"https://www.youtube.com/watch?v={video_id}",
                         "upload_status": response.get("status", {}),
                         "thumbnail_uploaded": False}
    record["state"] = "uploaded_pending_verification"
    _atomic_write(_safe_record_path(record_id, queue_dir), record)
    try:
        service.thumbnails().set(videoId=video_id,
                                 media_body=MediaFileUpload(str(thumb),
                                                            mimetype="image/png" if thumb.suffix.lower() == ".png" else "image/jpeg",
                                                            resumable=False)).execute()
        record["youtube"]["thumbnail_uploaded"] = True
        _atomic_write(_safe_record_path(record_id, queue_dir), record)
    except Exception:
        record["state"] = "uploaded_thumbnail_failed"
        record["error_note"] = "Video exists on YouTube; set thumbnail in Studio. Do not re-upload."
        _atomic_write(_safe_record_path(record_id, queue_dir), record)
        raise

    try:
        verified = service.videos().list(part="status,snippet", id=video_id).execute().get("items", [])
        status = verified[0].get("status", {}) if verified else {}
    except Exception:
        status = {}
    record["youtube"]["verified_status"] = status
    if status.get("privacyStatus") == "private" and status.get("publishAt") == approval["publish_at_utc"]:
        record["state"] = "scheduled"
    else:
        record["state"] = "uploaded_private_schedule_unverified"
        record["error_note"] = "Check YouTube Studio; do not assume future publication."
    _atomic_write(_safe_record_path(record_id, queue_dir), record)
    return record


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("connect", help="Google browser OAuth; store private token")
    commands.add_parser("channels", help="List channels authorized by OAuth")
    commands.add_parser("queue", help="Show local review/scheduling drafts")
    prep = commands.add_parser("prepare", help="Create review draft from render folder; NO upload")
    prep.add_argument("folder", type=Path)
    prep.add_argument("--title", default="")
    prep.add_argument("--description", default="")
    agree = commands.add_parser("approve", help="Approve exact files, channel and time; NO upload")
    agree.add_argument("id")
    agree.add_argument("--channel-id", required=True)
    agree.add_argument("--publish-at", required=True,
                       help="ISO datetime WITH offset, e.g. 2026-10-02T18:00:00+05:45")
    agree.add_argument("--made-for-kids", required=True, choices=("yes", "no"))
    schedule = commands.add_parser("schedule", help="UPLOAD and schedule only after explicit approval")
    schedule.add_argument("id")
    schedule.add_argument("--confirm", required=True, help="Exact phrase: SCHEDULE <id>")
    options = parser.parse_args()
    if options.command == "connect":
        result = oauth_connect()
    elif options.command == "channels":
        result = owned_channels(authenticated_service())
    elif options.command == "queue":
        result = [{"id": q["id"], "state": q["state"],
                   "title": q["metadata"]["title"], "approval": q.get("approval"),
                   "youtube": q.get("youtube")} for q in list_queue()]
    elif options.command == "prepare":
        result = prepare(options.folder, title=options.title, description=options.description)
    elif options.command == "approve":
        result = approve(options.id, channel_id=options.channel_id,
                         publish_at=options.publish_at,
                         made_for_kids=options.made_for_kids == "yes")
    else:
        result = upload_approved(options.id, confirmation=options.confirm)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()
