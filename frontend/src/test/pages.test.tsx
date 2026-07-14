// Tests for the workbench pages: evidence list/detail, Q&A, charts.
//
// Each test stubs the fetch surface so the pages render against a fake
// workbench server. The auth gate is implicitly exercised by going
// through the login form in the auth tests, so these focus on page-level
// happy paths and 403/404 handling.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SessionProvider } from "../auth/useAuth";
import { apiClient } from "../api/client";
import { EvidenceListPage } from "../pages/EvidenceListPage";
import { EvidenceDetailPage } from "../pages/EvidenceDetailPage";
import { QAPage } from "../pages/QAPage";
import { ChartsPage } from "../pages/ChartsPage";

function makeFetch(responseMap: Record<string, () => Response | Promise<Response>>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.replace(/^https?:\/\/[^/]+/, "").replace(/^\/+/, "/");
    const key = `${method} ${path.split("?")[0]}`;
    const responder = responseMap[key];
    if (!responder) {
      throw new Error(`unexpected fetch: ${key}`);
    }
    return responder();
  });
}

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderAt(node: React.ReactNode, initialRoute: string, queryClient = makeQueryClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <MemoryRouter initialEntries={[initialRoute]}>
          <Routes>
            <Route path="/evidence" element={<EvidenceListPage />} />
            <Route path="/evidence/:evidenceId" element={<EvidenceDetailPage />} />
            <Route path="/qa" element={<QAPage />} />
            <Route path="/charts" element={<ChartsPage />} />
            <Route path="/*" element={node} />
          </Routes>
        </MemoryRouter>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

function seedSession(): void {
  window.localStorage.setItem(
    "dafi-sentinel:session",
    JSON.stringify({ token: "tok-1", user_id: "user-1", display_name: "Ada", roles: ["analyst"] }),
  );
  apiClient.setToken("tok-1");
}

describe("evidence list", () => {
  beforeEach(() => {
    window.localStorage.clear();
    apiClient.setToken(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("renders the owned evidence", async () => {
    seedSession();
    const fetchStub = makeFetch({
      "GET /evidence": () =>
        new Response(
          JSON.stringify([
            {
              evidence_id: "ev-1",
              source_uri: "fixtures/incidents.jsonl",
              source_row: 1,
              source_offset: null,
              redacted_summary: "first event",
              timestamp: "2026-07-14T12:00:00Z",
              fields: {},
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/evidence");

    await waitFor(() => {
      expect(screen.getByText("ev-1")).toBeInTheDocument();
    });
  });

  it("shows the empty state when the actor owns no evidence", async () => {
    seedSession();
    const fetchStub = makeFetch({
      "GET /evidence": () => new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/evidence");

    await waitFor(() => {
      expect(screen.getByText(/no evidence yet/i)).toBeInTheDocument();
    });
  });
});

describe("evidence detail", () => {
  beforeEach(() => {
    window.localStorage.clear();
    apiClient.setToken(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("renders the evidence details", async () => {
    seedSession();
    const fetchStub = makeFetch({
      "GET /evidence/ev-1": () =>
        new Response(
          JSON.stringify({
            evidence_id: "ev-1",
            source_uri: "fixtures/incidents.jsonl",
            source_row: 1,
            source_offset: null,
            redacted_summary: "first event",
            timestamp: "2026-07-14T12:00:00Z",
            fields: { severity: "critical" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/evidence/ev-1");

    await waitFor(() => {
      expect(screen.getByText("ev-1")).toBeInTheDocument();
      expect(screen.getByText(/first event/)).toBeInTheDocument();
    });
  });

  it("shows a 403 message when the evidence belongs to another account", async () => {
    seedSession();
    const fetchStub = makeFetch({
      "GET /evidence/ev-private": () =>
        new Response(JSON.stringify({ detail: "forbidden" }), { status: 403 }),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/evidence/ev-private");

    await waitFor(() => {
      expect(screen.getByText(/403/i)).toBeInTheDocument();
    });
  });
});

describe("qa page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    apiClient.setToken(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("submits a question and shows the cited evidence", async () => {
    seedSession();
    const fetchStub = makeFetch({
      "POST /qa": () =>
        new Response(
          JSON.stringify({
            answer: "based on ev-1: payment latency",
            cited_evidence: [
              { evidence_id: "ev-1", source_uri: "fixtures/incidents.jsonl", score: 0.0 },
            ],
            session_id: "session-1",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/qa");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /ask/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/based on ev-1/)).toBeInTheDocument();
      expect(screen.getByText("ev-1")).toBeInTheDocument();
    });
  });
});

describe("charts page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    apiClient.setToken(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("renders a chart and surfaces the cited evidence count", async () => {
    seedSession();
    const pngBytes = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    const fetchStub = makeFetch({
      "POST /charts": () =>
        new Response(
          JSON.stringify({
            spec: {
              kind: "line",
              title: "Latency",
              x: "minute",
              y: "ms",
              evidence_ids: ["ev-1"],
            },
            png_base64: btoa(String.fromCharCode(...pngBytes)),
            cited_evidence: [{ evidence_id: "ev-1", source_uri: "", score: 0.0 }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/charts");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /render/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/cites 1 evidence/i)).toBeInTheDocument();
      // Recharts renders an SVG inside the chart frame.
      expect(document.querySelector(".recharts-wrapper")).toBeTruthy();
    });
  });
});
