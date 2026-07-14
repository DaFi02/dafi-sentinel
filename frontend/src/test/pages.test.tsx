// Tests for the workbench pages: evidence list/detail, Q&A, charts.
//
// Each test stubs the fetch surface so the pages render against a fake
// workbench server. The auth gate is implicitly exercised by going
// through the login form in the auth tests, so these focus on page-level
// happy paths and 403/404 handling.
//
// The CRIT-1 fix moved the session transport to an HttpOnly cookie.
// ``seedSessionViaCookie`` stubs the ``/sessions/me`` probe the
// ``SessionProvider`` uses to hydrate the user profile; the dashboard
// never reads or stores the token.

import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SessionProvider } from "../auth/useAuth";
import { EvidenceListPage } from "../pages/EvidenceListPage";
import { EvidenceDetailPage } from "../pages/EvidenceDetailPage";
import { QAPage } from "../pages/QAPage";
import { ChartsPage } from "../pages/ChartsPage";

function makeFetch(responseMap: Record<string, () => Response | Promise<Response>>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    // The CRIT-1 fix requires every request to opt into the cookie
    // transport. Pin the contract here so a future refactor that drops
    // ``credentials: 'include'`` fails the test instead of silently
    // breaking the dashboard.
    expect(init?.credentials).toBe("include");
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

/**
 * Stub a successful ``/sessions/me`` probe so the SessionProvider
 * hydrates the user profile. The cookie path is the dashboard path;
 * the test fetch stub does not need to inspect Set-Cookie because the
 * cookie is sent back on the same fetch instance in the real browser.
 */
function seedSessionResponse(): () => Response {
  return () =>
    new Response(
      JSON.stringify({
        user_id: "user-1",
        display_name: "Ada",
        roles: ["analyst"],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
}

describe("evidence list", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the owned evidence", async () => {
    const fetchStub = makeFetch({
      "GET /sessions/me": seedSessionResponse(),
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
    const fetchStub = makeFetch({
      "GET /sessions/me": seedSessionResponse(),
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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the evidence details", async () => {
    const fetchStub = makeFetch({
      "GET /sessions/me": seedSessionResponse(),
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
    const fetchStub = makeFetch({
      "GET /sessions/me": seedSessionResponse(),
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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submits a question and shows the cited evidence", async () => {
    const fetchStub = makeFetch({
      "GET /sessions/me": seedSessionResponse(),
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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a chart and surfaces the cited evidence count", async () => {
    const pngBytes = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    const fetchStub = makeFetch({
      "GET /sessions/me": seedSessionResponse(),
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
