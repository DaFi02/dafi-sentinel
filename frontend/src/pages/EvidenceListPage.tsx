import { Link } from "react-router-dom";

import { useEvidenceList } from "../api/queries";
import { ApiError } from "../api/client";

export function EvidenceListPage() {
  const query = useEvidenceList(true);

  if (query.isLoading) {
    return <p className="muted">loading evidence…</p>;
  }
  if (query.error instanceof ApiError && query.error.status === 401) {
    return <p className="error">session expired. please sign in again.</p>;
  }
  if (query.error) {
    return <p className="error">failed to load evidence: {query.error.message}</p>;
  }
  const records = query.data ?? [];
  if (records.length === 0) {
    return <p className="muted">No evidence yet for this account.</p>;
  }
  return (
    <main>
      <h2>Owned evidence</h2>
      {records.map((record) => (
        <article key={record.evidence_id} className="card">
          <h3>
            <Link to={`/evidence/${encodeURIComponent(record.evidence_id)}`}>{record.evidence_id}</Link>
          </h3>
          <p className="muted">
            {record.source_uri}
            {record.source_row !== null ? ` row ${record.source_row}` : ""}
          </p>
          <p>{record.redacted_summary}</p>
        </article>
      ))}
    </main>
  );
}
