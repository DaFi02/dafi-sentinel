// Thin fetch wrapper that sends the HttpOnly session cookie and surfaces
// a typed error envelope. The workbench server replies with
// ``{"detail": "..."}`` for non-2xx responses; the helper propagates
// that to the TanStack Query layer.
//
// The CRIT-1 fix removed the bearer token from the JSON body and from
// this client: the session is now an HttpOnly+SameSite=strict cookie
// the browser sends automatically when ``credentials: 'include'`` is
// set. The dashboard never reads or stores the token.

export type SessionResponse = {
  user_id: string;
  display_name: string;
  roles: string[];
};

export type EvidenceResponse = {
  evidence_id: string;
  source_uri: string;
  source_row: number | null;
  source_offset: number | null;
  redacted_summary: string;
  timestamp: string;
  fields: Record<string, unknown>;
};

export type CitedEvidence = {
  evidence_id: string;
  source_uri: string;
  score: number;
};

export type QAResponse = {
  answer: string;
  cited_evidence: CitedEvidence[];
  session_id: string;
};

export type ChartSpecPayload = {
  kind: "line" | "bar" | "scatter" | "table";
  title: string;
  x: string;
  y: string;
  evidence_ids: string[];
};

export type ChartResponse = {
  spec: ChartSpecPayload;
  png_base64: string;
  cited_evidence: CitedEvidence[];
};

export type RoleResponse = {
  user_id: string;
  display_name: string;
  roles: string[];
  permissions: string[];
};

export type AuditEntry = {
  id: string;
  actor_id: string;
  action: string;
  allowed: boolean;
  reason: string;
  timestamp: string;
  role_context: string[];
};

export type AuditsResponse = {
  audits: AuditEntry[];
};

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  constructor(status: number, detail: string) {
    super(`${status} ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

const BASE_URL = "/";

export class ApiClient {
  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    // ``credentials: 'include'`` is the cookie transport. The browser
    // attaches the HttpOnly ``dafi_sentinel_session`` cookie to every
    // same-origin request; the server reads it from ``request.cookies``.
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        ...(init.headers as Record<string, string> | undefined),
      },
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body && typeof body.detail === "string") {
          detail = body.detail;
        }
      } catch {
        // body is not JSON; keep statusText.
      }
      throw new ApiError(response.status, detail);
    }
    if (response.status === 204) {
      return undefined as unknown as T;
    }
    return (await response.json()) as T;
  }

  login(username: string, password: string): Promise<SessionResponse> {
    return this.request<SessionResponse>("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  }

  logout(): Promise<void> {
    // The cookie carries the session token; ``DELETE /sessions/me``
    // resolves it from the cookie and clears the cookie in the
    // response. The dashboard never needs to know the token value.
    return this.request<void>("/sessions/me", { method: "DELETE" });
  }

  me(): Promise<SessionResponse> {
    return this.request<SessionResponse>("/sessions/me");
  }

  listEvidence(): Promise<EvidenceResponse[]> {
    return this.request<EvidenceResponse[]>("/evidence");
  }

  getEvidence(evidenceId: string): Promise<EvidenceResponse> {
    return this.request<EvidenceResponse>(`/evidence/${encodeURIComponent(evidenceId)}`);
  }

  askQuestion(payload: { question: string; session_id: string; limit?: number }): Promise<QAResponse> {
    return this.request<QAResponse>("/qa", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  renderChart(payload: { spec: ChartSpecPayload; data: Array<[unknown, unknown]> }): Promise<ChartResponse> {
    return this.request<ChartResponse>("/charts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  getRoles(userId: string): Promise<RoleResponse> {
    return this.request<RoleResponse>(`/roles/${encodeURIComponent(userId)}`);
  }

  listAudits(): Promise<AuditsResponse> {
    return this.request<AuditsResponse>("/audits");
  }
}

export const apiClient = new ApiClient();
