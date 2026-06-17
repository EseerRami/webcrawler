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
```

## How it maps to the "method"

| Source method step                      | Here                                            |
| --------------------------------------- | ----------------------------------------------- |
| One prompt / one goal                   | `goal` argument                                 |
| Claude writes the script                | `claude_writer.ScriptWriter.generate`           |
| Subagents verify the work               | `ScriptWriter.review` + revise loop             |
| ElevenLabs voice (your clone)           | `elevenlabs_voice.VoiceSynthesizer`             |
| HeyGen avatar, finished video out       | `heygen_avatar.AvatarVideoGenerator`            |

The "verify frames with subagents" idea is implemented here as a
code-controlled **iterate → grade → revise** loop on the script: cheaper,
deterministic, and the highest-leverage place to verify quality before paying
for voice + avatar rendering. (Frame-level visual verification would be a
natural next step — see *Extending* below.)

## Setup

```bash
pip install -r social_media_generator/requirements.txt
cp social_media_generator/.env.example .env   # then fill in your keys
set -a; . ./.env; set +a                       # export them
```

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

# Tune format
python -m social_media_generator "..." --platform TikTok --seconds 30 --tone "calm, authoritative"
```

Outputs land in `output/<slug>/`:

- `script.json` — title, hook, body, CTA, narration, caption, hashtags + the review
- `narration.mp3` — the spoken track (full runs only)
- `video.mp4` — the finished avatar video (full runs only)
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

## Extending

- **Frame verification:** after the render, sample frames and have Claude (vision)
  check the avatar/branding, regenerating if needed — the literal "verify frames"
  loop from the source method.
- **B-roll / captions / SFX:** add a post-processing stage (e.g. ffmpeg) for
  burned-in captions, background music, and sound effects.
- **Multi-platform:** generate platform-specific captions/aspect ratios from the
  same script in one run.
