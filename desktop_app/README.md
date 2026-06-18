# Social Media Studio (desktop app)

An Electron desktop app for turning a goal into a finished talking-avatar video:
write a script with Claude, edit it, upload **your photo** (it becomes a
lip-synced presenter via HeyGen) and **product images**, and render it with
**your ElevenLabs voice** — polished into an edited video with HyperFrames.

```
Electron window (JS UI)
   │  HTTP on 127.0.0.1:8765
   ▼
FastAPI backend (Python)  ──▶  social_media_generator pipeline
   script → ElevenLabs voice → HeyGen talking-photo avatar → HyperFrames compose
```

## What each piece does

- **Script** — Claude writes and self-reviews it; you can edit every field before rendering.
- **Your photo** — uploaded to HeyGen as a *talking photo*, so your own face speaks the script. No need to pre-build an avatar in the HeyGen dashboard.
- **Product images** — handed to HyperFrames, which features them as product scenes/cutaways in the edit.
- **Your voice** — ElevenLabs; set `ELEVENLABS_VOICE_ID` to your cloned voice.
- **HyperFrames** — the automatic editor: arranges the avatar clip, product shots, captions, intro/outro into a finished video, with a vision-based frame check.

## Setup

```bash
# 1. Python deps (from the repo root)
pip install -r social_media_generator/requirements.txt
pip install -r desktop_app/requirements.txt

# 2. Keys (see social_media_generator/.env.example)
export ANTHROPIC_API_KEY=...        # script
export ELEVENLABS_API_KEY=...       # voice
export ELEVENLABS_VOICE_ID=...      # your cloned voice
export HEYGEN_API_KEY=...           # avatar (talking photo)

# 3. HyperFrames + ffmpeg for the polish/verify stage (optional but recommended)
npx skills add heygen-com/hyperframes
#   install ffmpeg too (e.g. brew install ffmpeg)

# 4. Electron deps
cd desktop_app/electron && npm install
```

## Run

```bash
# from desktop_app/electron
npm start
```

`main.js` spawns the Python backend for you (`uvicorn …:app --port 8765`) using
the `python` on your PATH. To manage the backend yourself instead:

```bash
SMG_SPAWN_BACKEND=0 npm start          # in one terminal
uvicorn desktop_app.backend.server:app --port 8765   # from repo root, another terminal
```

Env knobs: `SMG_BACKEND_PORT` (default 8765), `SMG_PYTHON` (python executable),
`SMG_SPAWN_BACKEND=0` (don't auto-spawn).

## Using it

1. **Script** — type a goal, click *Generate script*, edit the fields (the
   **narration** is what your voice will say).
2. **Assets** — choose your photo and any product images; toggle HyperFrames polish.
3. **Generate video** — watch progress; the finished video previews inline.

Generated files live under a per-job temp dir; the backend serves the playable
file at `/api/files/{job}/...`.

## Honest status

- The Python pipeline + backend are wired and import-clean; the Electron files
  pass `node --check`. I could **not** run the GUI or a real generation here (no
  API keys, headless env), so treat this as a working scaffold to run locally.
- HeyGen's **talking-photo** endpoints and the v2 character shape match current
  docs but should be confirmed against your HeyGen account — `heygen_avatar.py`
  surfaces raw API errors to make that easy.
- For packaging into a distributable `.app`/`.exe` (bundling Python), add
  electron-builder + a packaged Python (PyInstaller) as a follow-up.
