# ClipFarm + Chat On Steroids: no model API key

This fork adds a **human-in-the-loop external AI selection path** to ClippyMe.
ChatGPT reads an offline Whisper transcript through an MCP plugin, decides which
moments to clip, and sends validated timestamps back to the local renderer.
There is **no ChatGPT session scraping and no OpenAI/Gemini inference call** in
this mode. Normal ClippyMe Gemini jobs remain available separately.

## Status / limits

- The ClipFarm plugin is a **separate Chat On Steroids Plugins** connection.
  Connecting only CoS Core/Desktop does not register it in ChatGPT.
- Jobs are supervised conversation workflows, **not** unattended/headless
  ChatGPT inference. Account usage limits and provider terms still apply.
- Auto monitor and Zernio publishing in upstream ClippyMe are unchanged;
  they do **not** automatically use ChatGPT. Publishing is deliberately not
  exposed through this MCP plugin.
- Local Faster-Whisper and the full ClippyMe rendering stack require your own
  CPU/GPU and storage. The first model run may download weights. This avoids
  paid *inference APIs*, not compute or optional third-party publishing costs.
- Use footage you own or have permission to clip. Do not publish unreviewed
  third-party footage, and do not equate heuristic clip scores with guaranteed
  views or earnings.

## Windows prerequisites

1. Install Python **3.11**, FFmpeg with `ffprobe`, Git, and optionally Docker
   Desktop for the upstream rendering stack. The repository pins heavy ML
   dependencies and was designed/tested on Python 3.11; Python 3.14 may not
   support every native wheel.
2. From your `clippyme` checkout, create a dedicated environment:

   ```powershell
   uv python install 3.11
   uv venv --python 3.11 .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e .
   python -m pip install "mcp>=1.12,<3" "faster-whisper>=1.2,<2" "yt-dlp>=2026.6.9,<2027" "pydantic>=2.13,<3"
   # To render, also install the repository's heavyweight requirements:
   python -m pip install -r requirements.txt
   ```

   If this `uv` Python build does not provide pip, use `uv pip install -e .`
   and `uv pip install ...` instead, within the activated venv.
   Docker is a supported alternative for the renderer, but the custom MCP
   executable must use a Python interpreter with the above plugin packages.

3. Create an import directory for videos. Copy files there, or configure an
   existing **specific** directory you permit the plugin to read:

   ```powershell
   New-Item -ItemType Directory -Force .\data\clipfarm\imports
   $env:CLIPFARM_IMPORT_ROOT = (Resolve-Path .\data\clipfarm\imports).Path
   $env:CLIPFARM_DATA_DIR = (Resolve-Path .\data\clipfarm).Path
   $env:CLIPFARM_WHISPER_MODEL = 'small'
   $env:TRANSCRIPTION_PROVIDER = 'whisper'
   ```

   Video files, job state and approvals live under `data/clipfarm/`, which is
   git-ignored. Do not commit source videos, transcripts, local configuration,
   credentials, or creator data.

## Connect the **external** MCP plugin

Open Chat On Steroids **Settings → Plugins**, complete the separate Plugins
connector setup if its card asks you to, then add a custom **executable**
plugin. The supported CoS custom-executable mode takes a program and explicit
arguments, not an arbitrary GitHub URL.

- Executable: absolute path to `clippyme\.venv\Scripts\python.exe`.
- Arguments: **one** argument, the absolute path to
  `clippyme\clipfarm_mcp\server.py` (direct launch works even when CoS doesn't
  support a working-directory field).
- Working directory (if available): absolute path to the fork's root.
- Environment (if supported): `CLIPFARM_DATA_DIR`, `CLIPFARM_IMPORT_ROOT`,
  `CLIPFARM_WHISPER_MODEL`. If the UI does not support env entries, set them
  in the parent process environment or use an executable launcher which sets
  *fixed, locally reviewed* paths before starting Python. Avoid credentials
  on the command line.

The script bootstraps only its own checkout and `src/` onto the module path.
The plugin executes with ordinary OS permissions, **outside** CoS's approved-folder boundary, which is why
ClipFarm confines imports and job IDs itself.

After connecting the plugin locally, **refresh the Chat On Steroids Plugins
connector inside ChatGPT**. Verify that the `prepare_video`, `get_transcript`,
`submit_highlights`, `render_job`, and `approve_clips` tools appear. A Ready
status inside CoS alone does not prove ChatGPT has refreshed its tool list.

## Conversation workflow

1. Put a permitted source in `data/clipfarm/imports`, then call
   `prepare_video(source_path=..., rights_confirmed=true)`. For supported
   YouTube/Twitch/Kick videos, pass an HTTPS URL instead. URL downloads are
   best-effort, respect creator permission and platform rules, and can fail.
2. `get_job_status(job_id)` until `awaiting_selection`. Transcription uses
   local Faster-Whisper and does not require any model API key.
3. Read **all** pages of `get_transcript(job_id, offset, limit)`; optionally
   inspect visuals with `get_video_frame(job_id, seconds)`.
4. Submit up to 20 complete, 10–75s, non-overlapping moments with the existing
   `ViralClip` fields using `submit_highlights`. Clip score is a subjective
   editorial heuristic; the backend validates timestamps, word overlap and
   source duration. The submission is immutable once rendering starts.
5. Call `render_job(job_id)`; `get_job_status` shows the eventual result.
   Inspect `list_clips` and optional `get_video_frame(..., clip_index=...)`.
6. Review actual MP4s in the local `data/clipfarm/jobs/<id>/render/` folder.
   Call `approve_clips(job_id, clip_indices)` to record local approval only.
   Posting/scheduling requires separate explicit action in ClippyMe.

### Example clip-selection input

```json
{
  "shorts": [{
    "start": 18.5,
    "end": 57.5,
    "viral_score": 75,
    "viral_reason": "The speaker presents a specific surprising answer and completes the explanation.",
    "video_description_for_tiktok": "A useful takeaway from this conversation.",
    "video_description_for_instagram": "One interesting moment from the full discussion.",
    "video_title_for_youtube_short": "An unexpected answer",
    "viral_hook_text": "Here's the surprising part"
  }]
}
```

## Direct CLI handoff (without the MCP plugin)

If you already have a word-timestamped ClippyMe transcript and a selections
JSON, both entry points support `--transcript-file` + `--highlights-file`:

```powershell
python -m clippyme.pipeline.orchestrator --input ".\my_video.mp4" `
  --output ".\data\clipfarm\manual-output" `
  --transcript-file ".\transcript.json" `
  --highlights-file ".\highlights.json"
```

Both are required together and bypass any Gemini API request. Invalid clips
fail closed rather than silently falling back to Gemini/whole-video output.

## Smoke tests and troubleshooting

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m pytest tests/test_external_highlights.py tests/test_clipfarm_mcp.py -q
python -c "from clipfarm_mcp.server import mcp; print('ClipFarm MCP loaded')"
```

`mcp.run(transport="stdio")` writes protocol messages to stdout, so don't
redirect regular logging/print messages there. Child workers write separate
`prepare.log` / `render.log`. If a job fails, inspect its `status.json` and
these logs. For actual rendering, FFmpeg/ffprobe, the Python ML wheels, and
model weights must be installed. Docker is not a prerequisite for these
lightweight unit tests but is the upstream's supported full-runtime path.

## Security / account boundaries

- No browser extension changes, no intercepted ChatGPT session cookies,
  no programmatic extraction of ChatGPT output, and no claim of unlimited use.
- File paths are confined to a separately configured import root; job IDs
  are strict UUIDs. Video URLs use an allowlist and explicit rights confirmation.
- Renderer is invoked with argument arrays, not a shell. Model and publisher
  API keys are removed from spawned processes. The approved-clips tool cannot
  publish content.
- External CoS MCP plugins have OS-user privileges: keep this plugin local and
  grant it only the inputs you mean it to read.
