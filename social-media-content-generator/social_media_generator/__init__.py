"""Social media content generator.

One goal in -> a finished short-form video out, by chaining:
  Claude (script + self-review) -> ElevenLabs (voice) -> HeyGen (avatar video).
"""

from .config import Config
from .hyperframes_compose import HyperFramesComposer
from .pipeline import ContentPipeline, GenerationResult
from .schemas import FrameReview, ScriptReview, VideoScript

__all__ = [
    "Config",
    "ContentPipeline",
    "GenerationResult",
    "HyperFramesComposer",
    "VideoScript",
    "ScriptReview",
    "FrameReview",
]
