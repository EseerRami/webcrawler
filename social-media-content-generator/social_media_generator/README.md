# Social Media Content Generator

Turn a single goal into a finished short-form video — the same method as the
"Claude made this entire video by itself" workflow: Claude writes (and reviews)
the script, ElevenLabs voices it (optionally with a clone of your voice), and
HeyGen renders an AI avatar lip-synced to that audio.

```
   goal ──▶ Claude (write + self-review/revise) ──▶ script + caption + hashtags
                                                   │
                                                   ▼
                       ElevenLabs (text-to-speech) ──▶ narration.mp3
                                                   │
                                                   ▼
                  HeyGen (avatar + audio ──▶ render ──▶ poll) ──▶ video.mp4
                                                   │
                                                   ▼
        HyperFrames (HTML composition ──▶ render ──▶ verify frames) ──▶ final.mp4
```

## How it maps to the "method"

| Source method step                      | Here                                            |
| --------------------------------------- | ----------------------------------------------- |
| One prompt / one goal                   | `goal` argument                                 |
| Claude writes the script                | `claude_writer.ScriptWriter.generate`           |
| Subagents verify the work               | `ScriptWriter.review` + revise loop             |
| ElevenLabs voice (your clone)           | `elevenlabs_voice.VoiceSynthesizer`             |
| HeyGen avatar talking-head clip         | `heygen_avatar.AvatarVideoGenerator`            |
| HyperFrames skills / "verify the frames"| `hyperframes_compose.HyperFramesComposer`       |

The "verify with subagents" idea shows up twice as code-controlled
**iterate → grade → revise** loops: once on the **script** (cheap text review
before paying for rendering) and once on the **frames** (Claude vision inspects
sampled frames of the composited video and revises the HTML composition until
they pass).

## Setup

```bash
pip install -r social_media_generator/requirements.txt
cp social_media_generator/.env.example .env   # then fill in your keys
set -a; . ./.env; set +a                       # export them
```

For the **HyperFrames polish layer** (final compositing + frame verification)
you also need Node and ffmpeg:

```bash
npx skills add heygen-com/hyperframes   # installs the HyperFrames CLI + agent skills
# ffmpeg is used to sample frames for verification (e.g. `brew install ffmpeg`)
```

If ffmpeg isn't present, the composition still renders — frame verification is
just skipped. If Node/HyperFrames isn't present, run with `--no-compose` (the
HeyGen avatar clip becomes the final video).

You need a Claude API key for the script. For the full video you also need
ElevenLabs (`ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID`) and HeyGen
(`HEYGEN_API_KEY` + `HEYGEN_AVATAR_ID`). Grab the voice id from your ElevenLabs
voice library (use a cloned voice for "your" voice) and the avatar id from your
HeyGen avatars.

## Usage

```bash
# Full pipeline
python -m social_media_generator "Explain why compound interest beats timing the market"

# Just the script + caption (no paid video APIs)
python -m social_media_generator "..." --script-only

# Avatar clip only, skip the HyperFrames polish layer
python -m social_media_generator "..." --no-compose

# Tune format
python -m social_media_generator "..." --platform TikTok --seconds 30 --tone "calm, authoritative"
```

Outputs land in `output/<slug>/`:

- `script.json` — title, hook, body, CTA, narration, caption, hashtags + the review
- `narration.mp3` — the spoken track (full runs only)
- `video.mp4` — the HeyGen avatar clip (full runs only)
- `final.mp4` — the HyperFrames-composited final cut (when compositing runs)
- `composition/` — the authored `index.html`, the sampled `frames/`, and the raw render
- `result.json` — run summary

### As a library

```python
from social_media_generator import ContentPipeline

result = ContentPipeline().run("Three habits that quietly ruin your sleep")
print(result.video_path, result.review_score)
```

## Notes & honest caveats

- **It costs money.** Claude tokens, ElevenLabs characters, and HeyGen render
  credits are all billed by usage. Start with `--script-only` to iterate cheaply.
- **HeyGen's API shape changes.** The request/response fields in
  `heygen_avatar.py` match the v2 API at the time of writing; if a call returns
  a 4xx, check the linked HeyGen docs for the current schema.
- **You don't strictly need the most expensive model.** The pipeline defaults
  to `claude-opus-4-8`; set `SMG_MODEL=claude-sonnet-4-6` to trade some quality
  for lower cost on the script stage.

## The HyperFrames stage

[HyperFrames](https://github.com/heygen-com/hyperframes) is an open-source,
HTML-native video renderer that ships as Claude Code skills (`npx skills add
heygen-com/hyperframes` → `/hyperframes`, `/hyperframes-cli`, `/hyperframes-media`,
`/gsap`). You author a video as an HTML page — Tailwind for layout, GSAP for
motion, timelines registered on `window.__timelines` with `data-start` /
`data-duration` for frame-accurate timing — and `npx hyperframes render
index.html` produces an MP4.

Here it runs as the **polish layer after the avatar**: `HyperFramesComposer`
has Claude author an `index.html` that drops the HeyGen avatar clip in as the
base layer and animates an intro card, section captions, a lower-third, and an
outro CTA around it; renders via the CLI; samples frames with ffmpeg; and has
Claude (vision) verify them, revising the HTML and re-rendering until they pass.

> Not yet validated end-to-end: the exact `hyperframes` CLI flags and how it
> handles an embedded `<video>` layer should be checked against the current
> HyperFrames docs/repo. The render-output discovery and ffmpeg fallback are
> written defensively so failures surface clearly.

## Extending

- **Word-synced captions:** use `/hyperframes-media` (transcription) to time
  captions to the narration instead of spreading them across the runtime.
- **SFX / music:** add a post step for background music and sound effects.
- **Multi-platform:** generate platform-specific captions/aspect ratios from the
  same script in one run.
