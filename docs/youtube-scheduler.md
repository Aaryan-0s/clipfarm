# ClipFarm YouTube scheduler — human approval first

## What this does

For every completed compilation: **render + thumbnail → local review draft →
approve exact video/title/description/thumbnail/channel/date → explicit final
schedule confirmation → upload as private with `publishAt` → verify in Studio**.
This uses YouTube's own future publish scheduler, so ClipFarm and the PC do not
need to stay running once YouTube has accepted the schedule. No upload is
triggered by finishing a render or by the existing `approve_clips` MCP tool.

The working module is `clipfarm_mcp/youtube_scheduler.py`; Chat On Steroids
gets separate `youtube_schedule_prepare`, `youtube_schedule_queue`,
`youtube_connected_channels`, `youtube_schedule_approve` and
`youtube_schedule_submit` tools after the plugin is restarted. A new upload
requires a separate explicit `SCHEDULE <draft_id>` confirmation. The plain
local approval tool remains manual-only.

## One-time Google connection — you do this in Google's browser

1. Visit [Google Cloud Console](https://console.cloud.google.com/), create or
   select a project, and enable **YouTube Data API v3**.
2. Under Google Auth Platform, configure the OAuth consent screen. If the
   app is in Testing, add your Google account as a test user.
3. Create an OAuth client of application type **Desktop app** and download its
   JSON. Select the actual YouTube channel (or Brand Account) during Google
   consent, then verify its returned **UC... channel ID** before upload.
4. Save the downloaded JSON locally as:
   `ClipFarm_isolated/data/clipfarm/youtube_scheduler/credentials/oauth_desktop_client.json`
   This directory is Git-ignored. **Never paste passwords, client JSON or
   OAuth tokens in a chat, commit them to Git, or place them in public folders.**
5. From the ClipFarm repo on your Windows PC, run:

   ```powershell
   python -m pip install -r requirements-youtube.txt
   python -m clipfarm_mcp.youtube_scheduler connect
   python -m clipfarm_mcp.youtube_scheduler channels
   ```

The `connect` command opens the official Google sign-in and stores the token
locally in `data/clipfarm/youtube_scheduler/credentials/youtube_token.json`.
OAuth scopes: `youtube.upload` (upload/thumbnail) and `youtube.readonly`
(confirm your channel ID and inspect the uploaded video's status). You can
revoke access from your Google account whenever desired. If the token expires
or the app remains in Testing, you may need to reconnect.

## Create a local review draft for a finished render

For the Stewie v2 compilation:

```powershell
python -m clipfarm_mcp.youtube_scheduler prepare "D:\fmailyguy\Compilations\Stewie Top 5\Ranking v2" --title "Top 5 Funniest Stewie Moments" --description "Five Stewie moments, edited by @clipshanger70. #FamilyGuy #Stewie"
```

The output is a draft ID. It creates local queue JSON; **no account call or
upload occurs**. The render folder must have `render_manifest.json`, a final
MP4 and a matching PNG/JPG thumbnail. ClipFarm hashes both files for review.
The queue is in `data/clipfarm/youtube_scheduler/queue/`, ignored by Git.

After watching the MP4 and checking the title, description and thumbnail,
approve the chosen channel and your desired local posting time. Examples
below show an offset-aware local time; replace with *your* date/time and the
real channel ID returned by the `channels` command:

```powershell
python -m clipfarm_mcp.youtube_scheduler approve YOUR_DRAFT_ID --channel-id UC_YOUR_EXACT_CHANNEL_ID --publish-at "2026-10-02T18:00:00+05:45" --made-for-kids no
python -m clipfarm_mcp.youtube_scheduler queue
```

The time needs an explicit timezone offset and must be **at least 45 minutes
in the future**. `--made-for-kids` is required: specify the correct audience
designation for the individual video. Approval remains local only. The video
and thumbnail SHA-256 hashes and approved metadata are frozen so replacing
the files afterward blocks the upload.

Only when the user gives final permission to **upload and set this publishing
date**, submit the draft:

```powershell
python -m clipfarm_mcp.youtube_scheduler schedule YOUR_DRAFT_ID --confirm "SCHEDULE YOUR_DRAFT_ID"
```

The API upload body uses `status.privacyStatus=private` and the approved
ISO-8601 UTC `status.publishAt`. It also uploads the matching thumbnail and
checks the response. The queue records the returned YouTube video ID and
review status. If upload is interrupted, the record becomes
`upload_uncertain` and the tool **will not blindly retry**; inspect YouTube
Studio for a possible duplicate first. If thumbnail setting fails, the video
ID is retained so you can fix the existing upload in Studio.

## Important YouTube limitation — API project verification

According to the official YouTube Data API docs, videos uploaded through a
project created after **July 28, 2020** that has not passed YouTube's
compliance audit are **restricted to private**. Consequently, an apparent
successful API upload is not a promise that it will actually publish at the
chosen time. Check the video's visibility and scheduling in YouTube Studio;
an API compliance audit may be required to enable public release through this
client. Until then, the practical fallback is to upload/schedule manually in
**YouTube Studio** using the rendered MP4 and thumbnail.

The scheduling API only accepts `publishAt` when the upload is private and has
never previously been published; a past `publishAt` may publish instantly.
ClipFarm prevents past/too-soon times. Rights/Content ID claims can separately
limit television compilations and monetization. Nothing in this workflow
guarantees public availability, eligibility for monetization, or a specific
audience outcome.

## Official references

- Google desktop OAuth: https://developers.google.com/youtube/v3/guides/auth/installed-apps
- `videos.insert`: https://developers.google.com/youtube/v3/docs/videos/insert
- Video `status.publishAt`: https://developers.google.com/youtube/v3/docs/videos
- `thumbnails.set`: https://developers.google.com/youtube/v3/docs/thumbnails/set
- Private-only API project limitation: https://developers.google.com/youtube/v3/revision_history
