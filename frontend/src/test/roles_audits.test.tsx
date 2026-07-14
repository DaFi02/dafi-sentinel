// Tests for the roles and audits pages.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";

import { SessionProvider } from "../auth/useAuth";
import { apiClient } from "../api/client";
import { RolesPage } from "../pages/RolesPage";
import { AuditsPage } from "../pages/AuditsPage";

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
            <Route path="/roles" element={<RolesPage />} />
            <Route path="/audits" element={<AuditsPage />} />
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

describe("roles page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    apiClient.setToken(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("renders the actor's own role set", async () => {
    seedSession();
    const fetchStub = makeFetch({
      "GET /sessions/me": () =>
        new Response(
          JSON.stringify({ token: "tok-1", user_id: "user-1", display_name: "Ada", roles: ["analyst"] }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      "GET /roles/user-1": () =>
        new Response(
          JSON.stringify({
            user_id: "user-1",
            display_name: "Ada",
            roles: ["analyst"],
            permissions: ["tool:search", "chart:request"],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/roles");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /roles for ada/i })).toBeInTheDocument();
      expect(screen.getByText("analyst")).toBeInTheDocument();
      expect(screen.getByText("tool:search")).toBeInTheDocument();
    });
  });

  it("renders the empty state when the actor has no roles or permissions", async () => {
    seedSession();
    const fetchStub = makeFetch({
      "GET /sessions/me": () =>
        new Response(
          JSON.stringify({ token: "tok-1", user_id: "user-1", display_name: "Ada", roles: ["analyst"] }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      "GET /roles/user-1": () =>
        new Response(
          JSON.stringify({ user_id: "user-1", display_name: "Ada", roles: [], permissions: [] }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/roles");

    await waitFor(() => {
      expect(screen.getByText(/no roles/i)).toBeInTheDocument();
      expect(screen.getByText(/no permissions/i)).toBeInTheDocument();
    });
  });
});

describe("audits page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    apiClient.setToken(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("renders the actor's audit log", async () => {
    seedSession();
    const fetchStub = makeFetch({
      "GET /audits": () =>
        new Response(
          JSON.stringify({
            audits: [
              {
                id: "audit-1",
                actor_id: "user-1",
                action: "session.login",
                allowed: true,
                reason: "login succeeded",
                timestamp: "2026-07-14T12:00:00Z",
                role_context: [],
              },
              {
                id: "audit-2",
                actor_id: "user-1",
                action: "qa.answer",
                allowed: true,
                reason: "evidence cited",
                timestamp: "2026-07-14T12:01:00Z",
                role_context: ["user-1"],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/audits");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /audits/i })).toBeInTheDocument();
      expect(screen.getByText("session.login")).toBeInTheDocument();
      expect(screen.getByText("qa.answer")).toBeInTheDocument();
    });
  });

  it("shows the empty state when there are no audit records", async () => {
    seedSession();
    const fetchStub = makeFetch({
      "GET /audits": () =>
        new Response(JSON.stringify({ audits: [] }), { status: 200, headers: { "Content-Type": "application/json" } }),
    });
    vi.stubGlobal("fetch", fetchStub);

    renderAt(null, "/audits");

    await waitFor(() => {
      expect(screen.getByText(/no audit records yet/i)).toBeInTheDocument();
    });
  });
});
