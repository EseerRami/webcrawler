"""ElevenLabs text-to-speech: narration -> spoken audio (mp3).

Uses the documented ElevenLabs REST API directly via `requests` (no SDK
dependency). Point ELEVENLABS_VOICE_ID at any voice in your account — including
an instant/professional voice clone of yourself — to get the cloned narration
described in the source method.

Docs: https://elevenlabs.io/docs/api-reference/text-to-speech
"""

from __future__ import annotations

import requests

from .config import Config

_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class VoiceSynthesizer:
    def __init__(self, config: Config, timeout: int = 120):
        config.require_voice()
        self._config = config
        self._timeout = timeout

    def synthesize(self, text: str, out_path: str) -> str:
        """Render `text` to speech and write the mp3 to `out_path`. Returns the path."""
        url = _TTS_URL.format(voice_id=self._config.elevenlabs_voice_id)
        headers = {
            "xi-api-key": self._config.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self._config.elevenlabs_model_id,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self._timeout)
        if resp.status_code != 200:
            raise RuntimeError(
                f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:500]}"
            )

        with open(out_path, "wb") as f:
            f.write(resp.content)
        return out_path
