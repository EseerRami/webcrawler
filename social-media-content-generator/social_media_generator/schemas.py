"""Structured data the pipeline passes between stages.

These Pydantic models double as the JSON schemas Claude is constrained to when
generating the script and the self-review, so the rest of the code can rely on
the shapes instead of parsing free text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VideoScript(BaseModel):
    """A platform-ready short-form video script."""

    title: str = Field(description="Punchy title / headline for the video.")
    hook: str = Field(description="The first 1-2 lines that stop the scroll.")
    body: str = Field(description="The main content, conversational and spoken-word.")
    call_to_action: str = Field(description="What the viewer should do next.")
    narration: str = Field(
        description=(
            "The complete spoken script, exactly as it should be voiced — "
            "hook + body + call to action stitched into clean, natural speech. "
            "No stage directions, no markdown, no emojis."
        )
    )
    caption: str = Field(description="The post caption to publish alongside the video.")
    hashtags: list[str] = Field(
        default_factory=list, description="Relevant hashtags, without the # symbol."
    )


class ScriptReview(BaseModel):
    """A reviewer's verdict on a draft script — drives the revise loop."""

    approved: bool = Field(description="True if the script is good enough to produce.")
    score: int = Field(description="Overall quality from 1 (poor) to 10 (excellent).")
    issues: list[str] = Field(
        default_factory=list, description="Concrete problems that should be fixed."
    )
    suggestions: str = Field(
        default="", description="Actionable guidance for the next revision."
    )


class FrameReview(BaseModel):
    """A vision reviewer's verdict on sampled frames of the composited video."""

    approved: bool = Field(
        description="True if the rendered frames look correct and ready to ship."
    )
    issues: list[str] = Field(
        default_factory=list,
        description=(
            "Concrete visual problems: clipped/overlapping text, captions off-screen, "
            "mistimed overlays, unreadable contrast, broken layout, missing avatar, etc."
        ),
    )
    suggestions: str = Field(
        default="",
        description="Specific instructions for revising the HTML composition.",
    )
