"""Local MCP job safety and approval workflow; worker subprocess is mocked."""
import json

import pytest

from clipfarm_mcp import core
from test_external_highlights import clip, transcript_fixture


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    root = tmp_path / "clipfarm"
    imports = root / "imports"
    imports.mkdir(parents=True)
    monkeypatch.setattr(core, "DATA_ROOT", root)
    monkeypatch.setattr(core, "IMPORT_ROOT", imports)
    monkeypatch.setattr(core, "_spawn", lambda job_id, operation: 12345)
    return root, imports


def test_requires_permission_and_confines_files(isolated, tmp_path):
    _, imports = isolated
    source = imports / "movie.mp4"
    source.write_bytes(b"not yet a video")
    with pytest.raises(ValueError, match="confirm"):
        core.prepare_video(source_path=str(source))
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"not a video")
    with pytest.raises(ValueError, match="approved import"):
        core.prepare_video(source_path=str(outside), rights_confirmed=True)
    with pytest.raises(ValueError, match="HTTPS"):
        core.prepare_video(url="http://127.0.0.1/secret", rights_confirmed=True)


def test_submission_render_and_human_approval(isolated):
    root, imports = isolated
    source = imports / "movie.mp4"
    source.write_bytes(b"placeholder")
    created = core.prepare_video(source_path=str(source), rights_confirmed=True)
    job_id = created["job_id"]
    directory = root / "jobs" / job_id
    manifest = core._read(directory / "manifest.json")
    manifest.update(title="movie", duration=50, source_filename="source.mp4")
    core._atomic(directory / "manifest.json", manifest)
    core._atomic(directory / "transcript.json", transcript_fixture())
    core._atomic(directory / "status.json", {"phase": "awaiting_selection"})
    assert len(core.get_transcript(job_id, 0, 20)["words"]) == 20
    assert core.get_transcript(job_id, 0, 20)["next_offset"] == 20
    assert core.list_pending()[0]["job_id"] == job_id
    submitted = core.submit_highlights(job_id, [clip()])
    assert submitted["phase"] == "selected"
    assert core.render_job(job_id)["phase"] == "rendering"
    with pytest.raises(ValueError, match="awaiting"):
        core.submit_highlights(job_id, [clip()])
    rendered = directory / "render"
    rendered.mkdir()
    (rendered / "test.mp4").write_bytes(b"fake output")
    (rendered / "test_metadata.json").write_text(
        json.dumps({"shorts": [{"clip_filename": "test.mp4", "start": 3, "end": 25}]}), encoding="utf-8")
    core._atomic(directory / "status.json", {"phase": "ready_for_review"})
    assert core.list_clips(job_id)[0]["index"] == 0
    with pytest.raises(ValueError):
        core.approve_clips(job_id, [99])
    approved = core.approve_clips(job_id, [0])
    assert approved["publishing"] == "manual_only"
    assert core._read(directory / "approval.json")["approved_indices"] == [0]


def test_rejects_path_traversal(isolated):
    with pytest.raises(ValueError):
        core.job_dir("../../other")
    with pytest.raises(ValueError):
        core.job_dir("11111111-1111-1111-1111-111111111111")
