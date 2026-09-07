"""Claude-powered script writing and self-review.

This is the brain of the pipeline. Claude writes the script, then a second
Claude call critiques it against the original goal. If the critique isn't a
pass, we feed the feedback back in and let Claude revise — a small
iterate -> grade -> revise loop, the code-controlled analogue of the
"subagents that verify" idea from the source method.
"""

from __future__ import annotations

import anthropic

from .config import Config
from .schemas import ScriptReview, VideoScript

_WRITER_SYSTEM = """You are an expert short-form video scriptwriter for social media \
(YouTube Shorts, TikTok, Instagram Reels). You write tight, spoken-word scripts that \
hook in the first two seconds, deliver one clear idea, and end with a single call to \
action. The narration must read aloud naturally: contractions, short sentences, no \
markdown, no emojis, no stage directions, no "[pause]" markers. Write for the ear, not \
the eye."""

_REVIEWER_SYSTEM = """You are a demanding short-form video producer reviewing a draft \
script before it goes into expensive avatar+voice production. Judge it against the \
creator's goal: Does the hook actually stop the scroll? Is there one clear takeaway? \
Does the narration sound natural read aloud? Is the call to action specific? Be honest \
— only approve a script you'd actually ship. Score 1-10 and approve only at 8 or above."""


class ScriptWriter:
    def __init__(self, config: Config):
        config.require_script()
        self._config = config
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def generate(
        self,
        goal: str,
        platform: str = "YouTube Shorts",
        tone: str = "energetic and direct",
        target_seconds: int = 45,
        feedback: str | None = None,
    ) -> VideoScript:
        """Write a script for `goal`. If `feedback` is given, revise toward it."""
        prompt = (
            f"Create a {target_seconds}-second {platform} script.\n\n"
            f"GOAL: {goal}\n"
            f"TONE: {tone}\n\n"
            "Keep the narration to roughly "
            f"{int(target_seconds * 2.5)} words so it fits the runtime when spoken."
        )
        if feedback:
            prompt += (
                "\n\nThis is a revision. Address this reviewer feedback specifically:\n"
                f"{feedback}"
            )

        response = self._client.messages.parse(
            model=self._config.model,
            max_tokens=4000,
            system=_WRITER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=VideoScript,
        )
        return response.parsed_output

    def review(self, goal: str, script: VideoScript) -> ScriptReview:
        """Critique a draft script against the original goal."""
        prompt = (
            f"CREATOR'S GOAL: {goal}\n\n"
            "DRAFT SCRIPT (JSON):\n"
            f"{script.model_dump_json(indent=2)}\n\n"
            "Review it and return your verdict."
        )
        response = self._client.messages.parse(
            model=self._config.model,
            max_tokens=2000,
            system=_REVIEWER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=ScriptReview,
        )
        return response.parsed_output

    def write_reviewed_script(
        self,
        goal: str,
        max_revisions: int = 2,
        on_event=None,
        **gen_kwargs,
    ) -> tuple[VideoScript, ScriptReview]:
        """Generate, then revise until the reviewer approves or we run out of rounds.

        `on_event(stage, payload)` is an optional callback for progress logging.
        Returns the final script and the review that accompanied it.
        """

        def emit(stage: str, payload):
            if on_event:
                on_event(stage, payload)

        feedback: str | None = None
        script: VideoScript | None = None
        review: ScriptReview | None = None

        for attempt in range(max_revisions + 1):
            emit("draft_start", {"attempt": attempt + 1})
            script = self.generate(goal, feedback=feedback, **gen_kwargs)
            review = self.review(goal, script)
            emit(
                "draft_reviewed",
                {"attempt": attempt + 1, "score": review.score, "approved": review.approved},
            )
            if review.approved:
                break
            # Build feedback for the next round from the reviewer's notes.
            feedback = review.suggestions
            if review.issues:
                feedback = "Issues: " + "; ".join(review.issues) + "\n" + feedback

        assert script is not None and review is not None
        return script, review
