// Tests for the auth gate and login form.
//
// The tests use a stubbed `globalThis.fetch` so the React tree can run
// against a fake workbench server. The real FastAPI surface is
// exercised by the backend pytest suite; these tests pin the dashboard
// behavior in isolation.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import App from "../App";
import { SessionProvider } from "../auth/useAuth";
import { apiClient } from "../api/client";

function makeFetch(responseMap: Record<string, () => Response | Promise<Response>>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    // Strip the host (if any) and collapse duplicate leading slashes so
    // the lookup matches the keys callers pass in (e.g. `POST /sessions`).
    const path = url.replace(/^https?:\/\/[^/]+/, "").replace(/^\/+/, "/");
    const key = `${method} ${path.split("?")[0]}`;
    const responder = responseMap[key];
    if (!responder) {
      throw new Error(`unexpected fetch: ${key}`);
    }
    return responder();
  });
}

function renderApp(initialRoute: string, queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <MemoryRouter initialEntries={[initialRoute]}>
          <Routes>
            <Route path="/*" element={<App />} />
          </Routes>
        </MemoryRouter>
      </SessionProvider>
    </QueryClientProvider>,
  );
}

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

describe("auth gate", () => {
  beforeEach(() => {
    window.localStorage.clear();
    apiClient.setToken(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("redirects unauthenticated users to /login from a protected route", async () => {
    const fetchStub = makeFetch({
      "GET /sessions/me": () => new Response(JSON.stringify({ detail: "invalid" }), { status: 401 }),
    });
    vi.stubGlobal("fetch", fetchStub);

    const queryClient = makeQueryClient();
    renderApp("/evidence", queryClient);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    });
    expect(fetchStub).toHaveBeenCalled();
  });

  it("renders the protected shell when the session probe resolves", async () => {
    const fetchStub = makeFetch({
      "GET /sessions/me": () =>
        new Response(
          JSON.stringify({
            token: "tok-1",
            user_id: "user-1",
            display_name: "Ada",
            roles: ["analyst"],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      "GET /evidence": () => new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }),
    });
    vi.stubGlobal("fetch", fetchStub);

    const queryClient = makeQueryClient();
    renderApp("/evidence", queryClient);

    await waitFor(() => {
      expect(screen.getByText(/no evidence yet for this account/i)).toBeInTheDocument();
    });
  });

  it("submits the login form, stores the token, and navigates to the protected route", async () => {
    const fetchStub = makeFetch({
      "POST /sessions": () =>
        new Response(
          JSON.stringify({
            token: "tok-1",
            user_id: "user-1",
            display_name: "Ada",
            roles: ["analyst"],
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      "GET /sessions/me": () =>
        new Response(
          JSON.stringify({
            token: "tok-1",
            user_id: "user-1",
            display_name: "Ada",
            roles: ["analyst"],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      "GET /evidence": () => new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }),
    });
    vi.stubGlobal("fetch", fetchStub);

    const queryClient = makeQueryClient();
    renderApp("/login", queryClient);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/no evidence yet for this account/i)).toBeInTheDocument();
    });
    expect(window.localStorage.getItem("dafi-sentinel:session")).toContain("tok-1");
  });

  it("surfaces an api error on the login form when the credentials are wrong", async () => {
    const fetchStub = makeFetch({
      "POST /sessions": () =>
        new Response(JSON.stringify({ detail: "invalid credentials" }), { status: 401 }),
      "GET /sessions/me": () => new Response(JSON.stringify({ detail: "invalid" }), { status: 401 }),
    });
    vi.stubGlobal("fetch", fetchStub);

    const queryClient = makeQueryClient();
    renderApp("/login", queryClient);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument();
    });
  });
});
