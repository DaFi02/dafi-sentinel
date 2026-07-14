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
export default defineConfig({
  plugins: [react(), cspTogglePlugin()],
  server: {
    port: 5173,
    proxy: {
      // The dev server proxies API calls to the FastAPI workbench server
      // started via `uv run uvicorn dafi_sentinel.api.app:default_workbench_app`.
      "/sessions": "http://127.0.0.1:8000",
      "/evidence": "http://127.0.0.1:8000",
      "/qa": "http://127.0.0.1:8000",
      "/charts": "http://127.0.0.1:8000",
      "/roles": "http://127.0.0.1:8000",
      "/audits": "http://127.0.0.1:8000",
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
