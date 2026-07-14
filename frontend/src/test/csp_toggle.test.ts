// Tests for the DAFI_DEV_NO_CSP_META toggle (R2 high#7).
//
// The strict Content-Security-Policy meta tag in index.html blocks
// Vite HMR inline scripts, so the dev build needs an escape hatch.
// The cspTogglePlugin (registered in vite.config.ts via
// ``src/vite/csp-toggle.ts``) reads DAFI_DEV_NO_CSP_META at build
// time and removes the meta tag when the env var is set. Production
// builds (no env var) keep the strict CSP. This module pins the
// contract by exercising the pure helpers (``isCspSuppressed`` and
// ``toggleCspMeta``) directly — the plugin registration in
// ``vite.config.ts`` is verified at build time (``npx vite build``).

import { afterEach, describe, expect, it } from "vitest";

import {
  DAFI_CSP_TOGGLE_PLUGIN_NAME,
  cspTogglePlugin,
  isCspSuppressed,
  toggleCspMeta,
} from "../vite/csp-toggle";

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

describe("DAFI_DEV_NO_CSP_META toggle (pure helpers)", () => {
  it("treats the env var as inactive when undefined", () => {
    expect(isCspSuppressed(undefined)).toBe(false);
  });

  it("treats only the literal string '1' as active", () => {
    expect(isCspSuppressed("1")).toBe(true);
    expect(isCspSuppressed("0")).toBe(false);
    expect(isCspSuppressed("true")).toBe(false);
    expect(isCspSuppressed("")).toBe(false);
  });

  it("keeps the meta tag when suppress is false", () => {
    expect(toggleCspMeta(INDEX_HTML, false)).toBe(INDEX_HTML);
  });

  it("replaces the meta tag with a suppression comment when suppress is true", () => {
    const out = toggleCspMeta(INDEX_HTML, true);
    expect(out).not.toContain('http-equiv="Content-Security-Policy"');
    expect(out).toContain("DAFI_DEV_NO_CSP_META=1");
  });
});

describe("DAFI_DEV_NO_CSP_META toggle (plugin)", () => {
  const original = process.env.DAFI_DEV_NO_CSP_META;
  afterEach(() => {
    if (original === undefined) {
      delete process.env.DAFI_DEV_NO_CSP_META;
    } else {
      process.env.DAFI_DEV_NO_CSP_META = original;
    }
  });

  it("is named so the Vite plugin registry can find it", () => {
    expect(cspTogglePlugin().name).toBe(DAFI_CSP_TOGGLE_PLUGIN_NAME);
  });

  it("keeps the strict CSP meta tag when the env var is not set", () => {
    delete process.env.DAFI_DEV_NO_CSP_META;
    const plugin = cspTogglePlugin();
    const hook = plugin.transformIndexHtml as (html: string) => string | { html: string };
    const out = hook(INDEX_HTML);
    const html = typeof out === "string" ? out : out.html;
    expect(html).toContain('http-equiv="Content-Security-Policy"');
  });

  it("removes the strict CSP meta tag when DAFI_DEV_NO_CSP_META=1", () => {
    process.env.DAFI_DEV_NO_CSP_META = "1";
    const plugin = cspTogglePlugin();
    const hook = plugin.transformIndexHtml as (html: string) => string | { html: string };
    const out = hook(INDEX_HTML);
    const html = typeof out === "string" ? out : out.html;
    expect(html).not.toContain('http-equiv="Content-Security-Policy"');
    expect(html).toContain("DAFI_DEV_NO_CSP_META=1");
  });

  it("ignores the toggle when DAFI_DEV_NO_CSP_META is set to anything other than '1'", () => {
    process.env.DAFI_DEV_NO_CSP_META = "0";
    const plugin = cspTogglePlugin();
    const hook = plugin.transformIndexHtml as (html: string) => string | { html: string };
    const out = hook(INDEX_HTML);
    const html = typeof out === "string" ? out : out.html;
    expect(html).toContain('http-equiv="Content-Security-Policy"');
  });
});
