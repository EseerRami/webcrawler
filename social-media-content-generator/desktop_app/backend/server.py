"""FastAPI backend for the desktop app.

Bridges the Electron UI (JavaScript) to the Python `social_media_generator`
pipeline. Endpoints:

  GET  /api/health                 -> liveness + which integrations are configured
  POST /api/script                 -> generate (and review) a script from a goal
  POST /api/generate               -> start a video job (multipart: script JSON +
                                       face image + product images); returns job id
  GET  /api/jobs/{id}              -> job status + progress events + result
  GET  /api/files/{job}/{name}     -> serve a generated file (e.g. final.mp4) for preview

Run it:  uvicorn desktop_app.backend.server:app --port 8765
The Electron app can also spawn this automatically (see electron/main.js).
"""

from __future__ import annotations

import os
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from social_media_generator import Config, ContentPipeline
from social_media_generator.claude_writer import ScriptWriter
from social_media_generator.schemas import VideoScript

from .jobs import JobManager

app = FastAPI(title="Social Media Studio backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local desktop app
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS = JobManager()
WORK_ROOT = os.path.join(tempfile.gettempdir(), "smg_studio")
os.makedirs(WORK_ROOT, exist_ok=True)


@app.get("/api/health")
def health() -> dict:
    cfg = Config.from_env()
    return {
        "ok": True,
        "integrations": {
            "claude": bool(cfg.anthropic_api_key),
            "elevenlabs": bool(cfg.elevenlabs_api_key and cfg.elevenlabs_voice_id),
            "heygen": bool(cfg.heygen_api_key),
        },
    }


@app.post("/api/script")
def make_script(
    goal: str = Form(...),
    platform: str = Form("YouTube Shorts"),
    tone: str = Form("energetic and direct"),
    seconds: int = Form(45),
    max_revisions: int = Form(1),
) -> dict:
    cfg = Config.from_env()
    try:
        cfg.require_script()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    writer = ScriptWriter(cfg)
    script, review = writer.write_reviewed_script(
        goal,
        max_revisions=max_revisions,
        platform=platform,
        tone=tone,
        target_seconds=seconds,
    )
    return {"script": script.model_dump(), "review": review.model_dump()}


def _save_upload(upload: UploadFile, dest_dir: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    # basename guards against path traversal in the provided filename
    name = os.path.basename(upload.filename or "upload")
    path = os.path.join(dest_dir, name)
    with open(path, "wb") as f:
        f.write(upload.file.read())
    return path


@app.post("/api/generate")
async def generate(
    goal: str = Form(...),
    script_json: str = Form(...),
    seconds: int = Form(45),
    compose: bool = Form(True),
    max_frame_revisions: int = Form(2),
    face_image: UploadFile | None = File(None),
    product_images: list[UploadFile] = File(default=[]),
) -> dict:
    cfg = Config.from_env()
    try:
        cfg.require_voice()
        cfg.require_heygen()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        script = VideoScript.model_validate_json(script_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid script JSON: {e}")

    job = JOBS.create()
    job_dir = os.path.join(WORK_ROOT, job.id)
    assets_dir = os.path.join(job_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    face_path = _save_upload(face_image, assets_dir) if face_image else None
    product_paths = [_save_upload(p, assets_dir) for p in product_images if p.filename]

    def target(on_event=None) -> dict:
        result = ContentPipeline(cfg).run(
            goal=goal,
            script=script,
            output_dir=os.path.join(job_dir, "output"),
            make_video=True,
            compose=compose,
            max_frame_revisions=max_frame_revisions,
            face_image_path=face_path,
            product_image_paths=product_paths,
            target_seconds=seconds,
            on_event=on_event,
        )
        # Expose the playable file relative to /api/files/{job}.
        playable = result.final_video_path or result.video_path
        video_rel = (
            os.path.relpath(playable, job_dir).replace(os.sep, "/") if playable else None
        )
        return {"result": result.__dict__, "video_rel": video_rel}

    JOBS.run(job.id, target)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="No such job")
    return job.to_dict()


@app.get("/api/files/{job_id}/{rel_path:path}")
def serve_file(job_id: str, rel_path: str) -> FileResponse:
    job_dir = os.path.join(WORK_ROOT, job_id)
    # Resolve and confirm the path stays inside the job dir.
    full = os.path.realpath(os.path.join(job_dir, rel_path))
    if not full.startswith(os.path.realpath(job_dir) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(full)
