// Thin fetch wrapper that injects the bearer token and surfaces a
// typed error envelope. The workbench server replies with
// ``{"detail": "..."}`` for non-2xx responses; the helper propagates
// that to the TanStack Query layer.

export type SessionResponse = {
  token: string;
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
  private token: string | null = null;

  setToken(token: string | null): void {
    this.token = token;
  }

  getToken(): string | null {
    return this.token;
  }

  private headers(extra?: Record<string, string>): Record<string, string> {
    const headers: Record<string, string> = { ...(extra ?? {}) };
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }
    return headers;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: this.headers(init.headers as Record<string, string> | undefined),
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

  logout(token: string): Promise<void> {
    return this.request<void>(`/sessions/${token}`, { method: "DELETE" });
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
