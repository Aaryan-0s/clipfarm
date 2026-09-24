# ClipFarm edit-style presets — architecture and first reference study

## Product requirement

ClipFarm is a general-purpose source-to-clips platform. A Family Guy countdown
inspired by FuryBeez is ONE opt-in edit style, never the global default.
Football, streamer, interview, gaming, podcast and other formats must be free to
have independent layouts, durations, transition sounds and caption rules.
Do not hard-code Family Guy/FuryBeez into the core pipeline, MCP job contract,
transcription, highlight search or clip selection. Existing jobs and output
behaviour must remain backward-compatible.

## Reference study (2026-09-24)

Source: https://www.youtube.com/@FuryBeez/shorts. A flat channel index returned
446 Shorts. We downloaded and visually reviewed four representative videos:

- MXEBbwzovmc — Ranking Top 5 Times Peter Griffin Acted Childish (~68.4s)
- 6X3qe3J6fUQ — Ranking Worst Things To Happen To Peter Griffin (~68.7s)
- DuaMwCVC9EU — Ranking Peter Griffin Funniest Surgeries (~91.4s)
- y17JKqnvKmI — Ranking Funniest Birthday Party Moments (~67.9s)

This is a representative study, not a claim that all 446 Shorts were watched.
Store the catalogue and privately cached reference materials outside git under
`data/clipfarm/reference_furybeez/`. The reference videos are for analysis,
not for reuse as the user's source footage or re-publication.

Common visual observations from the four sampled Shorts:

- Portrait 9:16 presentation. A persistent top area carries a two-line,
  condensed italic all-caps ranking title with white/orange or white/green
  emphasis, dark outline and soft/high-contrast background.
- A five-row list sits below the headline. Start with numbered blank rows;
  reveal each short descriptive label as the corresponding moment plays.
- Original 16:9 animation/video fills the middle/lower stage horizontally,
  preserving the scene rather than aggressively cropping characters away.
- The bottom has a faint @FuryBeez identity watermark and stylized, typically
  very short/word-level dialogue captions in white with a dark outline.
- The composition persists through the ranked segments rather than creating a
  separate fullscreen title card at every scene. Background colour/blur can
  shift with the source scene.
- The ranking order and individual segment lengths vary; do not treat one
  sampled video's timing as a universal rule. The user's Family Guy request
  specifically requires five 15–20-second moments, including ~2 seconds after
  the main gag. That gives ~75–100s of scenes plus intro/transitions.

Audio requirement from user: a short SWISH/WHOOSH cue as the next ranked clip
begins. Implement an original or properly licensed cue; don't copy/repackage a
sound recording from the reference creator's video. Visually inspect and
aurally review a sample output to tune its duration and loudness against speech.

## Proposed isolated preset system

Shared pipeline (unchanged): authorised source ingestion -> local transcription
and word timestamps -> user/ChatGPT scene search and approved selections ->
source segment extraction -> general-purpose render orchestration -> manual
review. Each job stores a `style_id` and a per-job snapshot of style settings.
Older jobs without `style_id` follow the legacy renderer unchanged.

Suggested modules (names only; don't implement until review):

```
clipfarm_mcp/
  styles/
    registry.py               # register/query style IDs and versions
    models.py                 # validated style settings; default-safe
    renderer.py               # shared render contracts and transitions
    presets/
      default_v1.json         # legacy appearance/settings preserved
      cartoon_ranked_v1.json  # FuryBeez-inspired FAMILY GUY preset
      football_highlights_v1.json
      streamer_moments_v1.json
  assets/
    audio/
      whoosh_original_01.wav  # original/licensed, provenance recorded
```

The editor should offer an explicit style selector and preview. Preset fields:
`canvas`, `title_template`, `title_colour_slots`, `rank_count`, `rank_reveal`,
`font_family`, `text_outline`, `layout`, `background_blur`, `caption_style`,
`watermark`, `transition.video`, `transition.audio_asset`,
`transition.audio_gain_db`, `transition.audio_offset_ms`, `intro_seconds`,
`outro_seconds`, `max_scene_duration`, `render_quality`.

The input/source topic and intended list are project data, not part of the
preset: e.g. Family Guy / Peter / five scenes. Thus the same cartoon-ranked
preset can produce a different show without editing engine code.

### First preset: `cartoon_ranked_v1`

1. Default preview 1080x1920, 30fps or source-matched 24fps on CPU; configurable
   720x1280 fast export. Reserve top ~28–34% for persistent title + list.
2. Use condensed bold italic display text, high-contrast colour emphasis, thin
   black outline and blurred/gradient backing. No brand-specific watermark;
   watermark is user's channel identity if they supply it.
3. Rank list has five empty entries, updated as each clip plays. Rank and scene
   label animate into the appropriate row without obscuring important action.
4. Source video is uncropped/fit within the action stage by default; subject
   tracking is optional and must not cut off other characters.
5. Generate true word-timed dialogue captions; ensure source subtitles/credits
   do not result in unreadable overlapping text. Offer captions off if requested.
6. Between adjacent ranks: quick swish/woosh cue, optional 2–4-frame motion
   blur or slide, very short audio duck/limiter, avoid masking first spoken word.
   User controls cue gain and whether original dialogue carries across cut.
7. Preserve user's scene constraints separately (15–20s, complete setup/main
   gag, ~2-second reaction), check actual output durations and QA every export.
8. Build one sample comparison using existing five local Family Guy clips and
   review visual/audio timing before applying it to more videos.

## Future presets (different layouts, no global mutations)

- `football_highlights_v1`: score/time/team graphics, event replay, commentary,
  restrained transitions and optional crowd-audio handling; no cartoon rank
  board unless explicitly chosen.
- `streamer_moments_v1`: landscape gameplay plus facecam-safe layout,
  punch-in/reaction, chat-aware crop, clip context title, optional chat caption.
- `podcast_clean_v1`: speaker tracking, clean captions, less animation.

## Implementation order and acceptance criteria

1. Lock legacy render snapshots and tests. Extract reusable composition and
   audio transition functions WITHOUT replacing existing output behaviour.
2. Implement validated style registry + style snapshot at render time;
   reject unknown IDs and missing assets before starting an expensive job.
3. Build `cartoon_ranked_v1` template, ranking-list reveal and captions.
4. Add custom swish audio mix. Verify no clipped speech, no sudden level
   spikes; user can turn effect off and replace it with licensed assets.
5. Produce A/B sample from already-cut Family Guy clips. Review with user.
6. Add selector in dashboard and MCP API `style_id` as an optional parameter;
   unchanged default for all existing clients/jobs.
7. Test presets independently and replay an old job to confirm identical legacy
   behaviour. Future sports/streaming styles should be installable without
   altering Family Guy or the default renderer.

Status: REFERENCE REVIEW + DESIGN PLAN ONLY. This document does not switch a
default, overwrite any existing job, install assets, or publish content.
