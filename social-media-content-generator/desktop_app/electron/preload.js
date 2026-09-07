// Exposes the backend URL to the renderer without enabling node integration.
const { contextBridge } = require("electron");

const BACKEND_PORT = process.env.SMG_BACKEND_PORT || "8765";
contextBridge.exposeInMainWorld("studio", {
  backendUrl: `http://127.0.0.1:${BACKEND_PORT}`,
});
