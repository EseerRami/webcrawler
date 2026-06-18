"""Command-line entry point for the social media content generator.

Examples:

    # Full pipeline (script -> voice -> avatar video), keys read from env:
    python -m social_media_generator "Explain why compound interest beats timing the market"

    # Script + caption only, even if video keys are present:
    python -m social_media_generator "..." --script-only

    # Tune the format:
    python -m social_media_generator "..." --platform "TikTok" --seconds 30 --tone "calm and authoritative"
"""

from __future__ import annotations

import argparse
import sys

from .config import Config
from .pipeline import ContentPipeline


def _log(stage: str, payload) -> None:
    pretty = {
        "stage": lambda p: f"\n=== {p['name'].upper()} ===",
        "draft_start": lambda p: f"  Writing draft #{p['attempt']}...",
        "draft_reviewed": lambda p: (
            f"  Reviewed draft #{p['attempt']}: score {p['score']}/10 "
            f"({'approved' if p['approved'] else 'revising'})"
        ),
        "script_done": lambda p: f"  Script ready: {p['title']!r} (score {p['score']}/10)",
        "voice_done": lambda p: f"  Voice rendered -> {p['audio_path']}",
        "audio_uploaded": lambda p: "  Audio uploaded to HeyGen",
        "render_started": lambda p: f"  Avatar render started (id={p['video_id']})",
        "render_status": lambda p: f"  ...render status: {p['status']}",
        "video_done": lambda p: f"  Video rendered -> {p['video_path']}",
        "video_skipped": lambda p: f"  Video skipped: {p['reason']}",
        "compose_author": lambda p: f"  Authoring composition (round {p['attempt']})...",
        "compose_render": lambda p: f"  Rendering with HyperFrames (round {p['attempt']})...",
        "compose_verify_skipped": lambda p: f"  Frame verify skipped: {p['reason']}",
        "compose_verified": lambda p: (
            f"  Frames reviewed (round {p['attempt']}): "
            f"{'approved' if p['approved'] else 'revising'}"
            + (f" — {len(p['issues'])} issue(s)" if p["issues"] else "")
        ),
        "compose_done": lambda p: f"  Final cut -> {p['final_video_path']}",
    }
    fn = pretty.get(stage)
    if fn:
        print(fn(payload), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="social_media_generator",
        description="Generate a social media video from a single goal using "
        "Claude (script), ElevenLabs (voice), and HeyGen (avatar).",
    )
    parser.add_argument("goal", help="What the video should accomplish / be about.")
    parser.add_argument("--platform", default="YouTube Shorts")
    parser.add_argument("--tone", default="energetic and direct")
    parser.add_argument("--seconds", type=int, default=45, help="Target runtime.")
    parser.add_argument(
        "--max-revisions", type=int, default=2, help="Max review/revise rounds."
    )
    parser.add_argument("--output", default=None, help="Output directory.")
    parser.add_argument(
        "--script-only",
        action="store_true",
        help="Only write the script + caption; skip voice and video.",
    )
    parser.add_argument(
        "--no-compose",
        action="store_true",
        help="Skip the HyperFrames polish layer (avatar clip is the final video).",
    )
    parser.add_argument(
        "--max-frame-revisions",
        type=int,
        default=2,
        help="Max frame-verify/revise rounds for the HyperFrames composition.",
    )
    args = parser.parse_args(argv)

    config = Config.from_env()
    try:
        config.require_script()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    pipeline = ContentPipeline(config)
    try:
        result = pipeline.run(
            goal=args.goal,
            output_dir=args.output,
            make_video=False if args.script_only else None,
            compose=not args.no_compose,
            max_frame_revisions=args.max_frame_revisions,
            on_event=_log,
            platform=args.platform,
            tone=args.tone,
            target_seconds=args.seconds,
            max_revisions=args.max_revisions,
        )
    except Exception as e:  # surface integration errors cleanly
        print(f"\nerror: {e}", file=sys.stderr)
        return 1

    print("\n=== DONE ===")
    print(f"Output:      {result.output_dir}")
    print(f"Script:      {result.script_path}")
    if result.audio_path:
        print(f"Narration:   {result.audio_path}")
    if result.video_path:
        print(f"Avatar clip: {result.video_path}")
    if result.final_video_path:
        print(f"Final cut:   {result.final_video_path}")
    print(f"Review:      {result.review_score}/10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
