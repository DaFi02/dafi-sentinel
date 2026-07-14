// Tests for the auth gate and login form.
//
// The tests use a stubbed `globalThis.fetch` so the React tree can run
// against a fake workbench server. The real FastAPI surface is
// exercised by the backend pytest suite; these tests pin the dashboard
// behavior in isolation.
//
// The CRIT-1 fix moved the session transport from localStorage to an
// HttpOnly cookie. The dashboard never reads or stores the token, so
// these tests assert ``credentials: 'include'`` on every request and
// never touch localStorage.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import App from "../App";
import { SessionProvider } from "../auth/useAuth";

function makeFetch(responseMap: Record<string, () => Response | Promise<Response>>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    // The CRIT-1 fix requires every request to opt into the cookie
    // transport. Pin the contract here so a future refactor that drops
    // ``credentials: 'include'`` fails the test instead of silently
    // breaking the dashboard.
    expect(init?.credentials).toBe("include");
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
    // The CRIT-1 fix removed the localStorage session cache. The
    // dashboard hydrates the session from the HttpOnly cookie via
    // ``/sessions/me``, so the auth tests must not seed or clear
    // localStorage as a precondition.
  });

  afterEach(() => {
    vi.restoreAllMocks();
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

  it("submits the login form and navigates to the protected route via the cookie", async () => {
    const fetchStub = makeFetch({
      // The initial me probe MUST 401 so the LoginPage shows the
      // form instead of auto-redirecting to /evidence. After the
      // login POST succeeds, the session cache is refreshed and the
      // LoginPage navigates to /evidence.
      "GET /sessions/me": () => new Response(JSON.stringify({ detail: "invalid" }), { status: 401 }),
      "POST /sessions": () =>
        new Response(
          JSON.stringify({
            user_id: "user-1",
            display_name: "Ada",
            roles: ["analyst"],
          }),
          {
            status: 201,
            headers: {
              "Content-Type": "application/json",
              // The server sets the session cookie; the test stub
              // emulates that so the me probe succeeds on the next
              // refetch.
              "Set-Cookie": "dafi_sentinel_session=fake-token; HttpOnly; Path=/; SameSite=strict",
            },
          },
        ),
      "GET /evidence": () => new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }),
    });
    vi.stubGlobal("fetch", fetchStub);

    const queryClient = makeQueryClient();
    renderApp("/login", queryClient);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    });

    // R2 med: the form is no longer pre-filled. The user MUST type
    // the credentials before the submit button is enabled.
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "ada" } });
      fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "hunter2!" } });
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/no evidence yet for this account/i)).toBeInTheDocument();
    });
    // The CRIT-1 fix pins the contract: the dashboard MUST NOT store
    // the session token in localStorage. If a future refactor adds a
    // localStorage session cache, this assertion fails.
    expect(window.localStorage.getItem("dafi-sentinel:session")).toBeNull();
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

    // R2 med: the form requires explicit input now.
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "ada" } });
      fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "wrong" } });
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument();
    });
  });
});
