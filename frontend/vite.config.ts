/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite + Vitest share configuration: the React plugin powers the dev
// server, the Vitest block mounts the testing-library helpers and the
// jsdom environment that the PR5 dashboard tests need.
export default defineConfig({
  plugins: [react()],
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
    // R3 F1: forbid ``.only`` on any test or describe block. Vitest treats
    // an ``.only`` as a hard failure so a forgotten modifier cannot silently
    // shrink the suite. The 10-second ceiling guards the slow ResizeObserver
    // stub tests without making the fast tests wait.
    forbidOnly: true,
    testTimeout: 10_000,
  },
});
