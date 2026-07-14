import { useAudits } from "../api/queries";
import { ApiError } from "../api/client";

export function AuditsPage() {
  const audits = useAudits(true);

  if (audits.isLoading) {
    return <p className="muted">loading audits…</p>;
  }
  if (audits.error instanceof ApiError && audits.error.status === 401) {
    return <p className="error">session expired. please sign in again.</p>;
  }
  if (audits.error) {
    return <p className="error">failed to load audits: {audits.error.message}</p>;
  }
  const records = audits.data?.audits ?? [];
  if (records.length === 0) {
    return <p className="muted">No audit records yet.</p>;
  }
  return (
    <main>
      <h2>Audits</h2>
      {records.map((record) => (
        <article key={record.id} className="card">
          <h3>
            <code>{record.action}</code>{" "}
            <span className={record.allowed ? "muted" : "error"}>
              {record.allowed ? "allowed" : "denied"}
            </span>
          </h3>
          <p className="muted">
            {record.timestamp} · actor {record.actor_id}
            {record.role_context.length > 0 ? ` · roles ${record.role_context.join(", ")}` : ""}
          </p>
          <p>{record.reason}</p>
        </article>
      ))}
    </main>
  );
}
