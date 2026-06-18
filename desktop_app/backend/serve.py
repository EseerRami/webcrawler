"""Entry point for the bundled (PyInstaller) backend.

In development the Electron app spawns `python -m uvicorn ...`. When packaged,
there's no Python on the user's machine, so PyInstaller freezes this script into
a standalone `smg-backend` executable that Electron launches instead. It just
serves the same FastAPI `app` on the configured port.
"""

from __future__ import annotations

import os

import uvicorn

from desktop_app.backend.server import app


def main() -> None:
    port = int(os.environ.get("SMG_BACKEND_PORT", "8765"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
