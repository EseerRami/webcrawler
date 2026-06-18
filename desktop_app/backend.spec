# PyInstaller spec — freezes the FastAPI backend into a standalone executable.
#
# Run it from the desktop_app/electron dir (the npm "build:backend" script does):
#   pyinstaller --clean --noconfirm --distpath backend-bin --workpath build/pyi ../backend.spec
#
# Produces backend-bin/smg-backend (or smg-backend.exe), which electron-builder
# copies into the packaged app's resources/backend/ folder.

import os

# SPECPATH is provided by PyInstaller; it's the dir containing this spec (desktop_app).
ROOT = os.path.abspath(os.path.join(os.path.dirname(SPECPATH), ".."))

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("uvicorn", "anthropic", "fastapi", "starlette", "pydantic", "social_media_generator"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(ROOT, "desktop_app", "backend", "serve.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # The video pipeline shells out to ffmpeg / npx hyperframes at runtime; the
    # web-scraper deps in the repo aren't needed in the backend bundle.
    excludes=["selenium", "bs4", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="smg-backend",
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
