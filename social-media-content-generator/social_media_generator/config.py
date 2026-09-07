"""Configuration for the social media content generator.

All secrets are read from the environment so nothing sensitive lives in the
repo. The three integrations the pipeline uses:

  - Anthropic (Claude)  -> writes and reviews the script
  - ElevenLabs          -> turns the narration into a (cloned) voice track
  - HeyGen              -> renders an AI avatar lip-synced to that audio

Set the keys before running, e.g.:

    export ANTHROPIC_API_KEY=sk-ant-...
    export ELEVENLABS_API_KEY=...
    export ELEVENLABS_VOICE_ID=...        # the cloned voice to speak with
    export HEYGEN_API_KEY=...
    export HEYGEN_AVATAR_ID=...           # the avatar to render
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    # Claude / script generation
    anthropic_api_key: str | None = None
    model: str = "claude-opus-4-8"

    # ElevenLabs / voice
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model_id: str = "eleven_multilingual_v2"

    # HeyGen / avatar video
    heygen_api_key: str | None = None
    heygen_avatar_id: str | None = None
    heygen_avatar_style: str = "normal"
    video_width: int = 1280
    video_height: int = 720

    # HyperFrames / motion-graphics compositing (open-source HTML->MP4 renderer).
    # Installed as a Node CLI; see https://github.com/heygen-com/hyperframes
    hyperframes_cmd: str = "npx hyperframes"
    compose_fps: int = 30
    compose_resolution: str = "1920x1080"
    ffmpeg_cmd: str = "ffmpeg"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            model=os.environ.get("SMG_MODEL", "claude-opus-4-8"),
            elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY"),
            elevenlabs_voice_id=os.environ.get("ELEVENLABS_VOICE_ID"),
            elevenlabs_model_id=os.environ.get(
                "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
            ),
            heygen_api_key=os.environ.get("HEYGEN_API_KEY"),
            heygen_avatar_id=os.environ.get("HEYGEN_AVATAR_ID"),
            heygen_avatar_style=os.environ.get("HEYGEN_AVATAR_STYLE", "normal"),
            video_width=int(os.environ.get("SMG_VIDEO_WIDTH", "1280")),
            video_height=int(os.environ.get("SMG_VIDEO_HEIGHT", "720")),
            hyperframes_cmd=os.environ.get("HYPERFRAMES_CMD", "npx hyperframes"),
            compose_fps=int(os.environ.get("SMG_COMPOSE_FPS", "30")),
            compose_resolution=os.environ.get("SMG_COMPOSE_RESOLUTION", "1920x1080"),
            ffmpeg_cmd=os.environ.get("FFMPEG_CMD", "ffmpeg"),
        )

    def require_script(self) -> None:
        if not self.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. It is required to write the script."
            )

    def require_voice(self) -> None:
        if not self.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set (needed for voice).")
        if not self.elevenlabs_voice_id:
            raise RuntimeError(
                "ELEVENLABS_VOICE_ID is not set. Pick a voice (or your clone) in "
                "the ElevenLabs dashboard and export its id."
            )

    def require_avatar(self) -> None:
        if not self.heygen_api_key:
            raise RuntimeError("HEYGEN_API_KEY is not set (needed for the avatar video).")
        if not self.heygen_avatar_id:
            raise RuntimeError(
                "HEYGEN_AVATAR_ID is not set. Pick an avatar in HeyGen and export its id."
            )

    def require_heygen(self) -> None:
        """Looser check: just the API key. Used when a talking-photo (uploaded
        face image) supplies the character instead of a pre-made avatar id."""
        if not self.heygen_api_key:
            raise RuntimeError("HEYGEN_API_KEY is not set (needed for the avatar video).")

    @property
    def can_make_video(self) -> bool:
        return bool(
            self.elevenlabs_api_key
            and self.elevenlabs_voice_id
            and self.heygen_api_key
            and self.heygen_avatar_id
        )
