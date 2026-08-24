/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { cspTogglePlugin } from "./src/vite/csp-toggle";

// Vite + Vitest share configuration. The ``test`` field is augmented
// into Vite's ``InlineConfig`` by ``vitest/config`` but the augmentation
// does not propagate reliably through ``tsconfig.node.json`` (which has
// ``composite: true`` + ``skipLibCheck: true`` for project references).
// The runtime config is correct; the cast on ``test`` below silences the
// false-positive type error.
//
// R3 F1: forbid ``.only`` on any test or describe block. Vitest treats
// an ``.only`` as a hard failure so a forgotten modifier cannot silently
// shrink the suite. The 10-second ceiling guards the slow ResizeObserver
// stub tests without making the fast tests wait.
// Dev proxy target (D4): one env var shared by every API prefix so the
// containerized dev server can point at the api service while host runs
// keep the loopback default. Follows the ``csp-toggle.ts`` ``process.env``
// precedent — no ``loadEnv``/``.env`` files.
const API_TARGET = process.env.DAFI_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), cspTogglePlugin()],
  server: {
    port: 5173,
    proxy: {
      // The dev server proxies API calls to the FastAPI workbench server
      // started via `uv run uvicorn dafi_sentinel.api.app:default_workbench_app`.
      "/sessions": API_TARGET,
      "/evidence": API_TARGET,
      "/qa": API_TARGET,
      "/charts": API_TARGET,
      "/roles": API_TARGET,
      "/audits": API_TARGET,
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    forbidOnly: true,
    testTimeout: 10_000,
  } as never,
});
