// Electron main process.
//
// Creates the window and (optionally) spawns the Python FastAPI backend so the
// app is a single double-click to launch. If SMG_SPAWN_BACKEND=0, it assumes
// you started the backend yourself (uvicorn) and just connects to it.

const { app, BrowserWindow } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const http = require("http");

const BACKEND_PORT = process.env.SMG_BACKEND_PORT || "8765";
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const REPO_ROOT = path.resolve(__dirname, "..", "..");

let backendProc = null;

function spawnBackend() {
  if (process.env.SMG_SPAWN_BACKEND === "0") return;
  const py = process.env.SMG_PYTHON || "python";
  backendProc = spawn(
    py,
    ["-m", "uvicorn", "desktop_app.backend.server:app", "--port", BACKEND_PORT],
    { cwd: REPO_ROOT, env: process.env, stdio: "inherit" }
  );
  backendProc.on("error", (err) => {
    console.error("Failed to spawn backend:", err.message);
    console.error("Start it manually: uvicorn desktop_app.backend.server:app --port " + BACKEND_PORT);
  });
}

function waitForBackend(retries = 40) {
  return new Promise((resolve) => {
    const tick = (left) => {
      http
        .get(`${BACKEND_URL}/api/health`, (res) => {
          res.resume();
          resolve(true);
        })
        .on("error", () => {
          if (left <= 0) return resolve(false);
          setTimeout(() => tick(left - 1), 500);
        });
    };
    tick(retries);
  });
}

async function createWindow() {
  const win = new BrowserWindow({
    width: 1100,
    height: 820,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  await waitForBackend();
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(() => {
  spawnBackend();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (backendProc) backendProc.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProc) backendProc.kill();
});
