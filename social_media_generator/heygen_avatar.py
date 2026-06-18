"""HeyGen avatar video generation.

Flow:
  1. Upload the ElevenLabs mp3 to HeyGen as an asset so the avatar can lip-sync
     to that exact audio.
  2. Kick off a v2 video generation job (avatar + uploaded audio).
  3. Poll the status endpoint until the render completes, then download the mp4.

Docs: https://docs.heygen.com/reference/create-an-avatar-video-v2
      https://docs.heygen.com/reference/upload-asset
      https://docs.heygen.com/reference/video-status

HeyGen's API surface evolves; the field names below match the v2 API at the
time of writing. If a call 4xxs, check the linked docs for the current shape —
the request/response handling here is deliberately defensive so failures
surface clearly rather than silently.
"""

from __future__ import annotations

import time

import requests

from .config import Config

_UPLOAD_URL = "https://upload.heygen.com/v1/asset"
_TALKING_PHOTO_URL = "https://upload.heygen.com/v1/talking_photo"
_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
_STATUS_URL = "https://api.heygen.com/v1/video_status.get"


class AvatarVideoGenerator:
    def __init__(self, config: Config, timeout: int = 60):
        config.require_heygen()
        self._config = config
        self._timeout = timeout

    def _headers(self, content_type: str | None = "application/json") -> dict:
        headers = {"X-Api-Key": self._config.heygen_api_key}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def upload_talking_photo(self, image_path: str) -> str:
        """Upload a face/body photo and return a HeyGen talking_photo_id.

        This is how a user's own photo becomes a lip-synced presenter without
        pre-creating an avatar in the HeyGen dashboard.
        """
        ext = os.path.splitext(image_path)[1].lower()
        content_type = "image/png" if ext == ".png" else "image/jpeg"
        with open(image_path, "rb") as f:
            data = f.read()
        resp = requests.post(
            _TALKING_PHOTO_URL,
            headers=self._headers(content_type=content_type),
            data=data,
            timeout=self._timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"HeyGen talking-photo upload failed ({resp.status_code}): "
                f"{resp.text[:500]}"
            )
        body = resp.json().get("data", {})
        tp_id = body.get("talking_photo_id") or body.get("id")
        if not tp_id:
            raise RuntimeError(
                f"HeyGen talking-photo upload returned no id: {resp.text[:500]}"
            )
        return tp_id

    def _character(self, talking_photo_id: str | None) -> dict:
        if talking_photo_id:
            return {"type": "talking_photo", "talking_photo_id": talking_photo_id}
        if not self._config.heygen_avatar_id:
            raise RuntimeError(
                "No avatar to render: set HEYGEN_AVATAR_ID or supply a face photo "
                "(talking_photo_id)."
            )
        return {
            "type": "avatar",
            "avatar_id": self._config.heygen_avatar_id,
            "avatar_style": self._config.heygen_avatar_style,
        }

    def upload_audio(self, audio_path: str) -> str:
        """Upload an mp3 and return a HeyGen audio URL usable in a generate call."""
        with open(audio_path, "rb") as f:
            data = f.read()
        resp = requests.post(
            _UPLOAD_URL,
            headers=self._headers(content_type="audio/mpeg"),
            data=data,
            timeout=self._timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"HeyGen asset upload failed ({resp.status_code}): {resp.text[:500]}"
            )
        body = resp.json().get("data", {})
        url = body.get("url")
        if not url:
            raise RuntimeError(f"HeyGen upload returned no asset url: {resp.text[:500]}")
        return url

    def start_render(
        self, audio_url: str, title: str = "", talking_photo_id: str | None = None
    ) -> str:
        """Start an avatar video render against an uploaded audio url. Returns video_id.

        Pass `talking_photo_id` (from `upload_talking_photo`) to render the user's
        own photo; otherwise the configured HEYGEN_AVATAR_ID is used.
        """
        payload = {
            "video_inputs": [
                {
                    "character": self._character(talking_photo_id),
                    "voice": {"type": "audio", "audio_url": audio_url},
                }
            ],
            "dimension": {
                "width": self._config.video_width,
                "height": self._config.video_height,
            },
        }
        if title:
            payload["title"] = title

        resp = requests.post(
            _GENERATE_URL, headers=self._headers(), json=payload, timeout=self._timeout
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"HeyGen generate failed ({resp.status_code}): {resp.text[:500]}"
            )
        body = resp.json()
        video_id = body.get("data", {}).get("video_id")
        if not video_id:
            raise RuntimeError(f"HeyGen generate returned no video_id: {resp.text[:500]}")
        return video_id

    def wait_for_video(
        self,
        video_id: str,
        poll_seconds: int = 10,
        max_wait_seconds: int = 900,
        on_event=None,
    ) -> str:
        """Poll until the render finishes; return the downloadable video url."""
        deadline = time.monotonic() + max_wait_seconds
        while time.monotonic() < deadline:
            resp = requests.get(
                _STATUS_URL,
                headers=self._headers(content_type=None),
                params={"video_id": video_id},
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"HeyGen status failed ({resp.status_code}): {resp.text[:500]}"
                )
            data = resp.json().get("data", {})
            status = data.get("status")
            if on_event:
                on_event("render_status", {"status": status})

            if status == "completed":
                url = data.get("video_url")
                if not url:
                    raise RuntimeError("HeyGen reported completed but gave no video_url.")
                return url
            if status == "failed":
                raise RuntimeError(f"HeyGen render failed: {data.get('error')}")

            time.sleep(poll_seconds)

        raise TimeoutError(
            f"HeyGen render did not finish within {max_wait_seconds}s (video_id={video_id})."
        )

    def download(self, video_url: str, out_path: str) -> str:
        """Download a finished video to `out_path`."""
        resp = requests.get(video_url, timeout=self._timeout, stream=True)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Video download failed ({resp.status_code}): {resp.text[:200]}"
            )
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
        return out_path

    def render_from_audio(
        self,
        audio_path: str,
        out_path: str,
        title: str = "",
        talking_photo_id: str | None = None,
        on_event=None,
    ) -> str:
        """Convenience: upload -> render -> wait -> download. Returns the mp4 path."""
        audio_url = self.upload_audio(audio_path)
        if on_event:
            on_event("audio_uploaded", {"audio_url": audio_url})
        video_id = self.start_render(
            audio_url, title=title, talking_photo_id=talking_photo_id
        )
        if on_event:
            on_event("render_started", {"video_id": video_id})
        video_url = self.wait_for_video(video_id, on_event=on_event)
        return self.download(video_url, out_path)
