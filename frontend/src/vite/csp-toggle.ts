// R2 high#7: DAFI_DEV_NO_CSP_META toggle.
//
// The strict ``Content-Security-Policy`` meta tag shipped in
// ``index.html`` blocks Vite HMR inline scripts in dev mode. The
// toggle lets the dev server (and the test build) suppress the meta
// tag via an env var; production builds keep the strict CSP unless
// the operator opts out.
//
// This module is intentionally framework-agnostic so the test suite
// can exercise the plugin without importing ``vite.config.ts`` (which
// pulls in the React plugin, dev-server proxy, and the Vitest block —
// all of which TypeScript would have to type-check via a project
// reference). The plugin follows the Rollup ``transformIndexHtml``
// contract that Vite exposes.

import type { Plugin } from "vite";

export const DAFI_CSP_TOGGLE_PLUGIN_NAME = "dafi-csp-toggle";
export const DAFI_DEV_NO_CSP_META_ENV = "DAFI_DEV_NO_CSP_META";
const SUPPRESSED_COMMENT = "<!-- Content-Security-Policy suppressed: DAFI_DEV_NO_CSP_META=1 -->";
const CSP_META_PATTERN = /<meta\s+http-equiv="Content-Security-Policy"[^>]*\/?>/i;

export function isCspSuppressed(envValue: string | undefined): boolean {
  return envValue === "1";
}

export function toggleCspMeta(html: string, suppress: boolean): string {
  if (!suppress) {
    return html;
  }
  return html.replace(CSP_META_PATTERN, SUPPRESSED_COMMENT);
}

export function cspTogglePlugin(): Plugin {
  return {
    name: DAFI_CSP_TOGGLE_PLUGIN_NAME,
    transformIndexHtml(html) {
      const envValue = typeof process !== "undefined" ? process.env[DAFI_DEV_NO_CSP_META_ENV] : undefined;
      return toggleCspMeta(html, isCspSuppressed(envValue));
    },
  };
}
