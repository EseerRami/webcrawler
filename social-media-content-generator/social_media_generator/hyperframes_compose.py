"""HyperFrames compositing stage with a vision-based frame-verification loop.

HyperFrames (https://github.com/heygen-com/hyperframes) is an open-source,
HTML-native video renderer: you describe a video as an HTML page (Tailwind for
layout, GSAP for motion, timelines registered on `window.__timelines` with
`data-start` / `data-duration` for deterministic, frame-accurate timing), and
its CLI renders that HTML to an MP4.

Here we use it as a *polish layer on top of the HeyGen avatar clip*: Claude
authors an HTML composition that drops the avatar video in as the base layer and
animates an intro card, section captions, a lower-third, and an outro CTA around
it. We then render it with the `hyperframes` CLI, sample frames, and have Claude
(vision) verify them — revising the HTML and re-rendering until the frames pass
or we run out of rounds. That verify loop is the code-controlled version of the
"subagents verify the frames" step from the source method.

Requirements (external to pip):
  - Node + the HyperFrames CLI (`npx hyperframes ...`; install the Claude Code
    skills with `npx skills add heygen-com/hyperframes`).
  - ffmpeg, for sampling frames to verify. If ffmpeg is missing, the render
    still runs but frame verification is skipped (with a notice).

NOTE: the exact `hyperframes` CLI flags and the way it handles an embedded
`<video>` layer should be validated against the current HyperFrames docs/repo —
this module is written to the documented conventions but has not been run
end-to-end here. Render output discovery is deliberately defensive.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess

import anthropic

from .config import Config
from .schemas import FrameReview, VideoScript

_AUTHOR_SYSTEM = """You are a motion-graphics engineer who writes HyperFrames \
compositions. HyperFrames renders a single self-contained HTML file to a \
frame-accurate MP4. Follow these rules exactly:

- Output ONE complete, self-contained `index.html` and nothing else.
- Load Tailwind (browser runtime) and GSAP from CDNs in <head>.
- The stage is a full-viewport container sized to the target resolution.
- BASE LAYER: an HTML <video> element referencing the provided avatar video file \
by its relative filename, covering the full stage (object-fit: cover). The avatar \
clip already contains the voiceover audio.
- OVERLAYS (on top of the video): an intro title card, animated lower-third with \
the title, 2-4 short section captions that reinforce the narration, and an outro \
call-to-action card.
- PRODUCT IMAGES: if product image filenames are provided, feature each one as a \
clean product card/cutaway timed to the relevant part of the narration (e.g. slide \
in beside the presenter with a short label). Reference them by their relative \
filenames. Do not stretch them — preserve aspect ratio.
- MOTION: create every GSAP timeline with `{ paused: true }` and push it onto \
`window.__timelines` (define `window.__timelines = window.__timelines || []` first). \
Give animated elements `data-start` and `data-duration` (in seconds) so timing is \
deterministic. Spread overlays across the full target duration.
- Keep text large, high-contrast, and safely inside the frame (generous margins). \
No external assets other than the CDNs and the avatar video file.
- Do not include explanations or markdown fences in your answer — just the HTML."""

_AVATAR_FILENAME = "avatar.mp4"


def _strip_code_fence(text: str) -> str:
    """Return inner HTML if the model wrapped it in a ```...``` fence."""
    fence = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text.strip()


class HyperFramesComposer:
    def __init__(self, config: Config):
        config.require_script()  # authoring + vision both use Claude
        self._config = config
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    # --- authoring ------------------------------------------------------------
    def author_html(
        self,
        script: VideoScript,
        duration_seconds: int,
        product_filenames: list[str] | None = None,
        feedback: str | None = None,
    ) -> str:
        width, height = self._config.compose_resolution.split("x")
        products = product_filenames or []
        products_line = (
            "PRODUCT IMAGE FILES: " + ", ".join(products)
            if products
            else "PRODUCT IMAGE FILES: (none)"
        )
        prompt = (
            f"TARGET RESOLUTION: {width}x{height}\n"
            f"TARGET DURATION: about {duration_seconds} seconds\n"
            f"AVATAR VIDEO FILE (base layer): {_AVATAR_FILENAME}\n"
            f"{products_line}\n\n"
            "SCRIPT (JSON):\n"
            f"{script.model_dump_json(indent=2)}\n\n"
            "Write the index.html composition."
        )
        if feedback:
            prompt += (
                "\n\nThis is a revision. Fix these problems seen in the rendered "
                f"frames:\n{feedback}"
            )

        # Freeform HTML -> stream a plain completion (room for a full page).
        with self._client.messages.stream(
            model=self._config.model,
            max_tokens=16000,
            system=_AUTHOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()
        text = next((b.text for b in message.content if b.type == "text"), "")
        return _strip_code_fence(text)

    # --- rendering ------------------------------------------------------------
    def render(self, comp_dir: str, html_name: str = "index.html") -> str:
        """Render `comp_dir/html_name` to MP4 via the HyperFrames CLI. Returns path."""
        out_path = os.path.join(comp_dir, "composed.mp4")
        cmd = self._config.hyperframes_cmd.split() + [
            "render",
            html_name,
            "--output",
            "composed.mp4",
            "--fps",
            str(self._config.compose_fps),
            "--resolution",
            self._config.compose_resolution,
        ]
        proc = subprocess.run(
            cmd, cwd=comp_dir, capture_output=True, text=True, timeout=1800
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "HyperFrames render failed:\n"
                f"  cmd: {' '.join(cmd)}\n"
                f"  stderr: {proc.stderr[-800:]}\n"
                f"  stdout: {proc.stdout[-400:]}"
            )
        if os.path.exists(out_path):
            return out_path
        # Defensive: the CLI may name the output differently — grab the newest mp4.
        mp4s = [
            os.path.join(comp_dir, f) for f in os.listdir(comp_dir) if f.endswith(".mp4")
        ]
        mp4s = [p for p in mp4s if os.path.basename(p) != _AVATAR_FILENAME]
        if not mp4s:
            raise RuntimeError(
                "HyperFrames render reported success but produced no MP4 in "
                f"{comp_dir}. stdout: {proc.stdout[-400:]}"
            )
        return max(mp4s, key=os.path.getmtime)

    # --- frame verification ---------------------------------------------------
    def _ffmpeg_available(self) -> bool:
        return shutil.which(self._config.ffmpeg_cmd.split()[0]) is not None

    def sample_frames(self, video_path: str, frames_dir: str, count: int = 4) -> list[str]:
        """Extract `count` evenly-spaced frames as PNGs. [] if ffmpeg is missing."""
        if not self._ffmpeg_available():
            return []
        os.makedirs(frames_dir, exist_ok=True)
        pattern = os.path.join(frames_dir, "frame_%02d.png")
        # fps filter sampling is simple and robust without probing duration first.
        cmd = self._config.ffmpeg_cmd.split() + [
            "-y",
            "-i",
            video_path,
            "-vf",
            f"thumbnail,fps=1/2",
            "-frames:v",
            str(count),
            pattern,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            return []
        return sorted(
            os.path.join(frames_dir, f)
            for f in os.listdir(frames_dir)
            if f.startswith("frame_") and f.endswith(".png")
        )

    def verify_frames(
        self, goal: str, script: VideoScript, frame_paths: list[str]
    ) -> FrameReview:
        """Ask Claude (vision) whether the sampled frames are production-ready."""
        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"Goal: {goal}\n"
                    f"Title: {script.title}\n"
                    f"Call to action: {script.call_to_action}\n\n"
                    "These are sampled frames from the composited video (avatar + "
                    "motion-graphics overlays). Check for clipped or overlapping "
                    "text, captions running off-screen, unreadable contrast, broken "
                    "layout, a missing/covered avatar, or mistimed overlays. Approve "
                    "only if the frames look ready to publish."
                ),
            }
        ]
        for path in frame_paths:
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("utf-8")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": data,
                    },
                }
            )

        response = self._client.messages.parse(
            model=self._config.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": content}],
            output_format=FrameReview,
        )
        return response.parsed_output

    # --- orchestration --------------------------------------------------------
    def compose(
        self,
        goal: str,
        script: VideoScript,
        avatar_video_path: str,
        out_path: str,
        duration_seconds: int = 45,
        product_image_paths: list[str] | None = None,
        max_frame_revisions: int = 2,
        on_event=None,
    ) -> str:
        """Author -> render -> verify-frames -> revise loop. Returns final MP4 path."""

        def emit(stage: str, payload):
            if on_event:
                on_event(stage, payload)

        comp_dir = os.path.join(os.path.dirname(out_path) or ".", "composition")
        os.makedirs(comp_dir, exist_ok=True)
        shutil.copyfile(avatar_video_path, os.path.join(comp_dir, _AVATAR_FILENAME))

        # Copy product images into the composition dir under stable names.
        product_filenames: list[str] = []
        for i, src in enumerate(product_image_paths or []):
            ext = os.path.splitext(src)[1].lower() or ".png"
            name = f"product_{i + 1}{ext}"
            shutil.copyfile(src, os.path.join(comp_dir, name))
            product_filenames.append(name)

        feedback: str | None = None
        rendered: str | None = None

        for attempt in range(max_frame_revisions + 1):
            emit("compose_author", {"attempt": attempt + 1})
            html = self.author_html(
                script, duration_seconds, product_filenames, feedback=feedback
            )
            with open(os.path.join(comp_dir, "index.html"), "w") as f:
                f.write(html)

            emit("compose_render", {"attempt": attempt + 1})
            rendered = self.render(comp_dir)

            frames = self.sample_frames(rendered, os.path.join(comp_dir, "frames"))
            if not frames:
                emit("compose_verify_skipped", {"reason": "ffmpeg unavailable"})
                break

            review = self.verify_frames(goal, script, frames)
            emit(
                "compose_verified",
                {"attempt": attempt + 1, "approved": review.approved, "issues": review.issues},
            )
            if review.approved:
                break
            feedback = review.suggestions
            if review.issues:
                feedback = "Problems: " + "; ".join(review.issues) + "\n" + feedback

        assert rendered is not None
        shutil.copyfile(rendered, out_path)
        return out_path
