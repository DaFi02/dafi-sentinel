// @vitest-environment node
// Tests for the DAFI_DEV_NO_CSP_META toggle (R2 high#7).
//
// The strict Content-Security-Policy meta tag in index.html blocks
// Vite HMR inline scripts, so the dev build needs an escape hatch.
// The cspTogglePlugin (registered in vite.config.ts) reads
// DAFI_DEV_NO_CSP_META at build time and removes the meta tag when
// the env var is set. Production builds (no env var) keep the strict
// CSP. This module pins the contract end-to-end via the public Vite
// config so a future refactor cannot silently regress the toggle.

import { afterEach, describe, expect, it } from "vitest";
import { defineConfig } from "vite";

async function loadConfig() {
  // Re-import the config each test so the cached module picks up the
  // current process.env. The default export is a config builder (a
  // function or an object); resolve it before reading the plugins.
  const mod = await import("../../vite.config");
  const builder = mod.default;
  const resolved = typeof builder === "function" ? builder({ command: "serve", mode: "development" }) : builder;
  return resolved;
}

const INDEX_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'" />
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;

function findCspPlugin(plugins: unknown[]) {
  for (const plugin of plugins) {
    const candidate = plugin as { name?: string };
    if (candidate && candidate.name === "dafi-csp-toggle") {
      return plugin as { transformIndexHtml: (html: string) => string | { html: string } };
    }
  }
  throw new Error("dafi-csp-toggle plugin not registered");
}

describe("DAFI_DEV_NO_CSP_META toggle", () => {
  const original = process.env.DAFI_DEV_NO_CSP_META;
  afterEach(() => {
    if (original === undefined) {
      delete process.env.DAFI_DEV_NO_CSP_META;
    } else {
      process.env.DAFI_DEV_NO_CSP_META = original;
    }
  });

  it("keeps the strict CSP meta tag when the env var is not set", async () => {
    delete process.env.DAFI_DEV_NO_CSP_META;
    const config = await loadConfig();
    const plugin = findCspPlugin(config.plugins as unknown[]);
    const out = plugin.transformIndexHtml(INDEX_HTML);
    const html = typeof out === "string" ? out : out.html;
    expect(html).toContain('http-equiv="Content-Security-Policy"');
  });

  it("removes the strict CSP meta tag when DAFI_DEV_NO_CSP_META=1", async () => {
    process.env.DAFI_DEV_NO_CSP_META = "1";
    const config = await loadConfig();
    const plugin = findCspPlugin(config.plugins as unknown[]);
    const out = plugin.transformIndexHtml(INDEX_HTML);
    const html = typeof out === "string" ? out : out.html;
    expect(html).not.toContain('http-equiv="Content-Security-Policy"');
    expect(html).toContain("DAFI_DEV_NO_CSP_META=1");
  });

  it("ignores the toggle when DAFI_DEV_NO_CSP_META is set to anything other than '1'", async () => {
    process.env.DAFI_DEV_NO_CSP_META = "0";
    const config = await loadConfig();
    const plugin = findCspPlugin(config.plugins as unknown[]);
    const out = plugin.transformIndexHtml(INDEX_HTML);
    const html = typeof out === "string" ? out : out.html;
    expect(html).toContain('http-equiv="Content-Security-Policy"');
  });
});

// Reference defineConfig so vitest's TS resolver keeps the import
// (the config file uses defineConfig to type the plugins block).
defineConfig({ plugins: [] });
