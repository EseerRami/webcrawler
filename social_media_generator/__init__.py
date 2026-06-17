"""Social media content generator.

One goal in -> a finished short-form video out, by chaining:
  Claude (script + self-review) -> ElevenLabs (voice) -> HeyGen (avatar video).
"""

from .config import Config
from .pipeline import ContentPipeline, GenerationResult
from .schemas import ScriptReview, VideoScript

__all__ = [
    "Config",
    "ContentPipeline",
    "GenerationResult",
    "VideoScript",
    "ScriptReview",
]
