"""Offline approval gates for scheduling: no API calls before final confirmation."""
import json
from datetime import datetime, timezone

import pytest

from clipfarm_mcp import youtube_scheduler as ys

CHANNEL_ID = "UC" + "a" * 22


@pytest.fixture
def draft(tmp_path):
    renders = tmp_path / "Stewie Top 5"
    renders.mkdir()
    final = renders / "final.mp4"
    final.write_bytes(b"not a real MP4, tests do not upload actual media")
    thumbnail = renders / "thumbnail_1280x720.png"
    thumbnail.write_bytes(b"thumbnail")
    (renders / "render_manifest.json").write_text(
        json.dumps({"title": "Top 5 Stewie Moments", "final": str(final),
                    "thumbnail": str(thumbnail)}), encoding="utf8")
    queue = tmp_path / "queue"
    return ys.prepare(renders, queue_dir=queue), queue


def test_prepare_only_writes_local_draft(draft):
    record, queue = draft
    assert record["state"] == "awaiting_review"
    assert record["approval"] is None
    assert record["youtube"] is None
    assert ys.list_queue(queue)[0]["id"] == record["id"]


def test_preparing_same_video_does_not_create_duplicate_draft(draft):
    record, queue = draft
    again = ys.prepare(record["render_folder"], queue_dir=queue)
    assert again["id"] == record["id"]
    assert len(ys.list_queue(queue)) == 1


@pytest.mark.parametrize("time_str", ["2026-10-02T18:00:00", "2020-01-01T00:00:00Z",
                                           "not a date"])
def test_time_must_be_aware_and_future(time_str):
    with pytest.raises(ValueError):
        ys._publish_datetime(time_str, now=datetime(2026, 9, 26, tzinfo=timezone.utc))


def test_local_offset_converts_to_utc():
    output = ys._publish_datetime("2026-10-02T18:00:00+05:45",
                                  now=datetime(2026, 9, 26, tzinfo=timezone.utc))
    assert output == "2026-10-02T12:15:00Z"


def test_approved_file_cannot_be_changed(draft):
    record, queue = draft
    ys.approve(record["id"], channel_id=CHANNEL_ID,
               publish_at="2100-01-01T18:00:00+05:45", made_for_kids=False,
               queue_dir=queue)
    with open(record["video"]["path"], "ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="Reviewed file changed"):
        ys.upload_approved(record["id"], confirmation=f"SCHEDULE {record['id']}",
                           service=object(), queue_dir=queue)


def test_approval_is_not_upload_authorization(draft):
    record, queue = draft
    with pytest.raises(ValueError, match="confirmation"):
        ys.upload_approved(record["id"], confirmation="yes", service=object(), queue_dir=queue)
    ys.approve(record["id"], channel_id=CHANNEL_ID,
               publish_at="2100-01-01T18:00:00+05:45", made_for_kids=False,
               queue_dir=queue)
    with pytest.raises(ValueError, match="Final explicit confirmation"):
        ys.upload_approved(record["id"], confirmation="sure", service=object(), queue_dir=queue)
    assert ys._record(record["id"], queue)["state"] == "approved"


class _Call:
    def __init__(self, result=None, error=None):
        self.result = result or {}
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class _Upload:
    def __init__(self, api):
        self.api = api

    def next_chunk(self):
        if self.api.fail_upload:
            raise RuntimeError("network disrupted")
        return None, {"id": "test123abc45", "status": {"privacyStatus": "private"}}


class FakeService:
    def __init__(self, publish_at, *, fail_upload=False, fail_thumbnail=False):
        self.publish_at = publish_at
        self.fail_upload = fail_upload
        self.fail_thumbnail = fail_thumbnail
        self.insert_calls = []
        self.thumbnail_calls = []

    def channels(self):
        return self

    def videos(self):
        return self

    def thumbnails(self):
        return self

    def list(self, **kwargs):
        if kwargs.get("mine"):
            return _Call({"items": [{"id": CHANNEL_ID, "snippet": {"title": "My test channel"}}]})
        return _Call({"items": [{"status": {"privacyStatus": "private",
                                              "publishAt": self.publish_at}}]})

    def insert(self, **kwargs):
        self.insert_calls.append(kwargs)
        return _Upload(self)

    def set(self, **kwargs):
        self.thumbnail_calls.append(kwargs)
        return _Call(error=RuntimeError("no custom thumbnail permission")
                     if self.fail_thumbnail else None)


def _approved(draft):
    record, queue = draft
    rec = ys.approve(record["id"], channel_id=CHANNEL_ID,
                     publish_at="2100-01-01T18:00:00+05:45", made_for_kids=False,
                     queue_dir=queue)
    return rec, queue


def test_upload_requires_exact_confirm_and_schedules_private(draft):
    record, queue = _approved(draft)
    service = FakeService(record["approval"]["publish_at_utc"])
    result = ys.upload_approved(record["id"], confirmation=f"SCHEDULE {record['id']}",
                                service=service, queue_dir=queue)
    assert result["state"] == "scheduled"
    body = service.insert_calls[0]["body"]
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"] == "2100-01-01T12:15:00Z"
    assert body["snippet"]["title"] == "Top 5 Stewie Moments"
    assert result["youtube"]["thumbnail_uploaded"] is True
    assert len(service.insert_calls) == len(service.thumbnail_calls) == 1
    with pytest.raises(ValueError, match="Already attempted"):
        ys.upload_approved(record["id"], confirmation=f"SCHEDULE {record['id']}",
                           service=service, queue_dir=queue)


def test_upload_error_never_auto_retries(draft):
    record, queue = _approved(draft)
    service = FakeService(record["approval"]["publish_at_utc"], fail_upload=True)
    with pytest.raises(RuntimeError, match="network disrupted"):
        ys.upload_approved(record["id"], confirmation=f"SCHEDULE {record['id']}",
                           service=service, queue_dir=queue)
    assert ys._record(record["id"], queue)["state"] == "upload_uncertain"
    with pytest.raises(ValueError, match="Already attempted"):
        ys.upload_approved(record["id"], confirmation=f"SCHEDULE {record['id']}",
                           service=service, queue_dir=queue)


def test_thumbnail_failure_retains_youtube_video_id(draft):
    record, queue = _approved(draft)
    service = FakeService(record["approval"]["publish_at_utc"], fail_thumbnail=True)
    with pytest.raises(RuntimeError, match="custom thumbnail"):
        ys.upload_approved(record["id"], confirmation=f"SCHEDULE {record['id']}",
                           service=service, queue_dir=queue)
    latest = ys._record(record["id"], queue)
    assert latest["state"] == "uploaded_thumbnail_failed"
    assert latest["youtube"]["video_id"] == "test123abc45"
    assert latest["youtube"]["thumbnail_uploaded"] is False


def test_wrong_channel_refused_before_upload(draft):
    record, queue = _approved(draft)
    service = FakeService(record["approval"]["publish_at_utc"])
    rec = ys._record(record["id"], queue)
    rec["approval"]["channel_id"] = "UC" + "b" * 22
    ys._atomic_write(ys._safe_record_path(record["id"], queue), rec)
    with pytest.raises(ValueError, match="not the channel approved"):
        ys.upload_approved(record["id"], confirmation=f"SCHEDULE {record['id']}",
                           service=service, queue_dir=queue)
    assert service.insert_calls == []
