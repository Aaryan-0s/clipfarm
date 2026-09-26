# ClipFarm — Family Guy Ranking Template Rules

**Template:** `family_guy_ranked_v2` (new opt-in template; implementation specification)  
**Channel watermark:** `@clipshanger70`  
**Scope:** Every new Family Guy ranking video. Do not change the ClipFarm default renderer, football, streamer, or other formats.  
**Release rule:** Render and save locally for review; no YouTube upload or publication without the user's separate approval.

## 1. Format and persistent layout

- Vertical 9:16 video, target 720 × 1280 or higher, with H.264 video and AAC audio.
- **No intro or separate title card.** Start directly on the first ranked scene.
- Keep the bold outlined headline at the top, a fixed **left-aligned ranking list** with the slots `1.` through `5.`, and the main episode footage below it.
- Keep the headline and earlier revealed entries visible while new scenes play; never reorder the positions of the list rows.
- Use short, legible dialogue captions over the episode footage, away from the ranking list and watermark.
- Preserve the source footage's aspect ratio. Where necessary, use a blurred/color-coordinated background to fill the vertical stage; do not stretch people or crop away the joke's action.

## 2. Nonstandard playback sequence — mandatory

**Play the scenes in this exact sequence: `#2 → #3 → #4 → #5 → #1`.**

- The first frame begins with **#2 footage**, not a lead-in or preview of #1.
- Play #3, #4 and #5 next. **#1 must be the final video clip**, not the first.
- The board's numeric rows remain in their normal displayed positions `1, 2, 3, 4, 5`; playback order and board order are different concepts.
- Begin with all descriptive labels blank. Type in a label when its corresponding scene plays; prior labels stay visible.
- Do not reveal #1's name or show #1's footage before the final scene.
- Keep a separate explicit `playback_order: [2, 3, 4, 5, 1]` in the source plan and render manifest. Never assume a numeric sort will produce the correct edit.

## 3. Rank-label typing animation

- Each new ranking **label** must visibly type on character by character; no instantaneous pop-in. The slot number stays visible and stable.
- Begin typing shortly after the incoming scene starts, using approximately 0.5–1.5 seconds, adjusted to the label's length and mobile readability.
- Keep each completed label visible for the remaining scenes. A subtle temporary highlight of the active row is acceptable.
- The persistent title does not need to type. Keep rows within the safe area without wrapping onto the footage.
- Pair the visible typing with a **typing sound** synchronized with the character reveals. Five separate typing sequences, one per rank, including #2.
- Typing audio is independent of transition swishes. A separate brief rank-completion accent is optional, but does not replace typing audio.

## 4. User-supplied swish: exact edit-boundary timing

**Use the new swish SFX supplied by the user. Never use or silently fall back to the old generated `original_swisshhh.wav` or `original_whoosh.wav`.**

**Approved asset location:** `D:\fmailyguy\ClipFarm Templates\Audio\transition_swish_approved.mp3`

**Original supplied filename:** `dheerajakam4jor-swoosh-sound-effect-for-fight-scenes-or-transitions-2-149890.mp3`

**SHA-256:** `D2A6E6EB3191C0498637B24897B420717BCAE71C4B73F1AB5237DB9C47A802F6`

**Asset properties:** MP3, 48 kHz, mono, about 0.36 seconds. The original was moved into the template's Audio folder without changing its bytes.

- There are exactly **four** transition swishes: `#2→#3`, `#3→#4`, `#4→#5`, and `#5→#1`. No swish before #2 and no automatic swish after #1.
- Align the **audible onset / perceptual attack** of the supplied swish to the **exact visual cut frame where the incoming ranked scene begins**. The scene change controls the swish timing—not when the label starts typing or finishes.
- Derive every scene-change timestamp from the actual cumulative duration of the preceding rendered clips; do not use fixed absolute times or an estimated clip length.
- Check and trim/compensate for leading silence in the supplied file so the sound lands on the cut. Target an onset within one rendered frame (about 42 ms at 24 fps). If using a subtle preroll, the main accent still lands at the cut.
- Preserve original dialogue: mix/duck the sound to prevent masking speech, clipping or abrupt level jumps.
- Store or explicitly reference the approved original sound file in the template's assets. Record its exact filename/path and SHA-256 hash in the style snapshot and final manifest. Do not modify the source audio asset.
- **If the supplied SFX is unavailable, stop the render and request its path.** Do not substitute an older or guessed effect.
- Verify the **exported** audio at all four transition boundaries by listening and/or inspecting short audio windows. Merely listing the effect in JSON is insufficient.

## 5. Channel watermark

**Exact watermark text: `@clipshanger70`.**

- Add it to every frame of each new Family Guy ranking video, consistently sized/positioned and legible without obscuring faces, main action, captions, or the ranking board.
- Use the user's screenshot as visual direction: bold, semi-transparent warm yellow/olive text with a subtle dark outline/shadow. Adjust opacity/placement for readability without losing consistency.
- If a thumbnail contains a watermark, use this same exact handle.
- Do **not** use `STEWIE-GUY`, `@stewie-guy`, `FuryBeez`, or a reference creator's identity. Those were examples, not the channel watermark.

## 6. Thumbnail required with every video

- **Create a new matching thumbnail/cover image for every completed ranking video** as a normal output step, not a special one-off request.
- Recommended standard thumbnail: **1280 × 720 PNG or JPG**, with an optional 9:16 cover variant when needed.
- Match the *actual* topic and scenes. Use an expressive real frame from the source where practical; a generated composition is a concept image, not an episode still.
- Visual direction from the user's reference: a strong red headline banner, large condensed white uppercase topic text with dark outline/shadow, clean colorful scene composition, and a subtle `@clipshanger70` watermark.
- Check legibility at mobile size, correct title, accurate character/scene representation, safe cropping, and consistency with the final MP4.
- Save it in the same per-video folder as `thumbnail_1280x720.png` (or `.jpg`). Do not reuse a prior video's image.

## 7. Research and joke-aware scene selection

For each fresh video topic:

1. Research relevant episode scenes/cutaways and public online references. Public views are popularity signals, **not** another channel's private audience-retention data.
2. Find the matching scene in `D:\fmailyguy\Family Guy - Seasons 1 to 20`; use the user's local episode footage as the rendering source, not the online reference video.
3. Confirm visuals and dialogue, then select five genuinely distinct moments relevant to the chosen theme.
4. Identify the minimum understandable setup, escalation, gag/payoff, and useful reaction/aftermath. End before unrelated material or the next scene.
5. Choose each duration separately; **do not force 25–30 seconds or a fixed 10-second aftermath** if it weakens the joke.
6. Record episode ID, local source path, precise source ranges, descriptive label, cut rationale and the selected final #1 in `source_plan.json`.
7. Inspect transcripts and frames; correct obvious transcription mistakes and avoid incomplete speech or accidental scene repetitions.

## 8. Mandatory files for every topic

```text
<topic_folder>/
  final_ranked_video.mp4
  thumbnail_1280x720.png
  source_plan.json
  render_manifest.json
  qa_report.md
  _style_assets/
    preset_snapshot.json
    rank_label_overlays_or_animation/
    typing_sound_asset
    user_supplied_swish_asset
    captions/
  individual_clips/
```

The manifest must record `playback_order: [2, 3, 4, 5, 1]`, actual durations and boundary timestamps, exact watermark, thumbnail path, five typing events, four swish events, and the chosen new swish's filename/path plus SHA-256 hash.

## 9. Completion / QA checklist

- [ ] First frame is #2 footage with no intro; footage order is `2,3,4,5,1`.
- [ ] #1's label and footage appear only in the final scene.
- [ ] Board rows stay fixed; earlier labels persist and all five new labels animate via typing.
- [ ] The typing audio is audible and synchronized with each of the five label reveals.
- [ ] All **four** swishes use the **new user-supplied** sound, not the old synthesized one.
- [ ] Each swish attack lands on the frame where the incoming scene actually replaces the prior scene (within one frame).
- [ ] Episode dialogue remains clear and there are no audio peaks/dropouts at cuts.
- [ ] The exact watermark `@clipshanger70` appears consistently and does not cover the gag.
- [ ] A correctly themed thumbnail exists for this video and uses the correct channel name.
- [ ] Joke setups/payoffs and relevant reactions are complete, with scene-specific durations.
- [ ] Subtitles are accurate/readable and source characters are not distorted/cropped badly.
- [ ] Full MP4 decodes; inspect representative frames and each transition's video/audio.
- [ ] Source plan, manifest, original SFX reference, style snapshot, individual clips and thumbnail are saved.
- [ ] Nothing is uploaded or published to YouTube without the user's explicit review and approval.

## 10. Implementation status

This Markdown document records **requirements**. Its presence does **not** mean existing videos have been re-rendered or that the current renderer already implements playback reordering, typewriter audio/visuals, the supplied sound, watermark or automatic thumbnails. Build and verify this as a new **opt-in Family Guy template**, preserving the old renders and all unrelated ClipFarm formats.
