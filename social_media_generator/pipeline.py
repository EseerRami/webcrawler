"""End-to-end orchestration: one goal in, a finished video (and post) out.

Stages:
  1. Claude writes a script and self-reviews/revises it.
  2. ElevenLabs voices the narration.
  3. HeyGen renders an avatar lip-synced to that audio.
  4. Everything (script, caption, audio, video, metadata) is written to an
     output folder.

If the voice/avatar keys aren't configured, the pipeline still produces the
script + caption so you get value without the paid video APIs.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from .claude_writer import ScriptWriter
from .config import Config
from .elevenlabs_voice import VoiceSynthesizer
from .heygen_avatar import AvatarVideoGenerator
from .schemas import ScriptReview, VideoScript


@dataclass
class GenerationResult:
    goal: str
    output_dir: str
    script_path: str
    audio_path: str | None
    video_path: str | None
    review_score: int
    review_approved: bool


def _slugify(text: str, max_len: int = 40) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:max_len] or "video"


class ContentPipeline:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.from_env()

    def run(
        self,
        goal: str,
        output_dir: str | None = None,
        make_video: bool | None = None,
        on_event=None,
        **script_kwargs,
    ) -> GenerationResult:
        def emit(stage: str, payload):
            if on_event:
                on_event(stage, payload)

        if output_dir is None:
            output_dir = os.path.join("output", _slugify(goal))
        os.makedirs(output_dir, exist_ok=True)

        # 1. Script (with self-review/revise loop) ---------------------------
        emit("stage", {"name": "script"})
        writer = ScriptWriter(self.config)
        script, review = writer.write_reviewed_script(
            goal, on_event=on_event, **script_kwargs
        )
        script_path = os.path.join(output_dir, "script.json")
        self._write_script(script, review, goal, script_path)
        emit("script_done", {"title": script.title, "score": review.score})

        audio_path: str | None = None
        video_path: str | None = None

        # Decide whether to attempt the video legs.
        if make_video is None:
            make_video = self.config.can_make_video

        if make_video:
            # 2. Voice -------------------------------------------------------
            emit("stage", {"name": "voice"})
            audio_path = os.path.join(output_dir, "narration.mp3")
            VoiceSynthesizer(self.config).synthesize(script.narration, audio_path)
            emit("voice_done", {"audio_path": audio_path})

            # 3. Avatar video -----------------------------------------------
            emit("stage", {"name": "video"})
            video_path = os.path.join(output_dir, "video.mp4")
            AvatarVideoGenerator(self.config).render_from_audio(
                audio_path, video_path, title=script.title, on_event=on_event
            )
            emit("video_done", {"video_path": video_path})
        else:
            emit(
                "video_skipped",
                {"reason": "voice/avatar credentials not fully configured"},
            )

        result = GenerationResult(
            goal=goal,
            output_dir=output_dir,
            script_path=script_path,
            audio_path=audio_path,
            video_path=video_path,
            review_score=review.score,
            review_approved=review.approved,
        )
        with open(os.path.join(output_dir, "result.json"), "w") as f:
            json.dump(asdict(result), f, indent=2)
        return result

    @staticmethod
    def _write_script(
        script: VideoScript, review: ScriptReview, goal: str, path: str
    ) -> None:
        with open(path, "w") as f:
            json.dump(
                {
                    "goal": goal,
                    "script": script.model_dump(),
                    "review": review.model_dump(),
                },
                f,
                indent=2,
            )
