import { Link, useParams } from "react-router-dom";

import { useEvidence } from "../api/queries";
import { ApiError } from "../api/client";

export function EvidenceDetailPage() {
  const { evidenceId } = useParams<{ evidenceId: string }>();
  const query = useEvidence(evidenceId ?? null, true);

  if (query.isLoading) {
    return <p className="muted">loading evidence…</p>;
  }
  if (query.error instanceof ApiError) {
    if (query.error.status === 401) {
      return <p className="error">session expired. please sign in again.</p>;
    }
    if (query.error.status === 403) {
      return <p className="error">403 — this evidence belongs to another account.</p>;
    }
    if (query.error.status === 404) {
      return <p className="error">404 — evidence not found.</p>;
    }
  }
  if (query.error) {
    return <p className="error">failed to load evidence: {query.error.message}</p>;
  }
  const record = query.data;
  if (!record) {
    return <p className="muted">no evidence</p>;
  }
  const datasetName = record.fields["dataset.name"];
  const isHdfsBenchmark = datasetName === "LogHub HDFS_v1";
  const traceId = record.fields["dataset.trace_id"];
  const label = record.fields["dataset.label"];
  const labelSemantics = record.fields["dataset.label_semantics"];
  const version = record.fields["dataset.version"];
  const checksum = record.fields["dataset.checksum"];
  return (
    <main>
      <p>
        <Link to="/evidence">← back to evidence</Link>
      </p>
      <h2>{record.evidence_id}</h2>
      <p className="muted">
        {record.source_uri}
        {record.source_row !== null ? ` row ${record.source_row}` : ""}
        {record.source_offset !== null ? ` offset ${record.source_offset}` : ""}
      </p>
      <p>
        <strong>timestamp:</strong> {record.timestamp}
      </p>
      <p>
        <strong>redacted summary:</strong> {record.redacted_summary}
      </p>
      {isHdfsBenchmark ? (
        <section aria-label="Public benchmark provenance">
          <h3>Public benchmark provenance</h3>
          <p><strong>Dataset:</strong> LogHub HDFS_v1</p>
          <p><strong>Original trace ID:</strong> {String(traceId)}</p>
           <p><strong>Benchmark label:</strong> {String(label)}</p>
           <p><strong>Source attribution:</strong> {record.source_uri}</p>
           <p><strong>Source version:</strong> {String(version)}</p>
           <p><strong>Source checksum:</strong> {String(checksum)}</p>
           <p role="note">{String(labelSemantics)}</p>
        </section>
      ) : null}
      {Object.keys(record.fields).length > 0 ? (
        <section>
          <h3>fields</h3>
          <ul>
            {Object.entries(record.fields).map(([key, value]) => (
              <li key={key}>
                <code>
                  {key}: {JSON.stringify(value)}
                </code>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
