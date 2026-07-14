import "@testing-library/jest-dom/vitest";

// Recharts renders a ResponsiveContainer that watches layout changes via
// ResizeObserver. jsdom does not provide it, so the test environment
// stubs a no-op observer that immediately reports a non-zero size, which
// is enough to make the ResponsiveContainer commit its children in tests.
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe(target: Element): void {
      // Fire a single synthetic resize so ResponsiveContainer commits its
      // children (otherwise it stays at 0×0 and the SVG is never rendered).
      queueMicrotask(() => {
        const entry = {
          target,
          contentRect: { width: 800, height: 300, top: 0, left: 0, right: 800, bottom: 300, x: 0, y: 0, toJSON() { return {}; } },
          borderBoxSize: [],
          contentBoxSize: [],
          devicePixelContentBoxSize: [],
        };
        for (const callback of this._callbacks) {
          callback([entry as unknown as ResizeObserverEntry], this);
        }
      });
    }
    unobserve(): void {}
    disconnect(): void {}
    private _callbacks: ResizeObserverCallback[] = [];
    constructor(callback: ResizeObserverCallback) {
      this._callbacks.push(callback);
    }
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}
