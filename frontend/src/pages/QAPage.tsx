import { FormEvent, useState } from "react";

import { useAskQuestion } from "../api/queries";
import { ApiError } from "../api/client";

export function QAPage() {
  const [question, setQuestion] = useState("What triggered the incident?");
  const [sessionId, setSessionId] = useState("session-1");
  const ask = useAskQuestion(true);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    ask.reset();
    try {
      await ask.mutateAsync({ question, session_id: sessionId, limit: 5 });
    } catch {
      // surfaced via ask.error
    }
  };

  return (
    <main>
      <h2>Ask a question</h2>
      <form onSubmit={(event) => void onSubmit(event)}>
        <label htmlFor="qa-question">question</label>
        <textarea
          id="qa-question"
          className="textarea"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={3}
        />
        <label htmlFor="qa-session">session id</label>
        <input
          id="qa-session"
          className="input"
          value={sessionId}
          onChange={(event) => setSessionId(event.target.value)}
        />
        <button className="button" type="submit" disabled={ask.isPending}>
          {ask.isPending ? "asking…" : "ask"}
        </button>
      </form>
      {ask.error instanceof ApiError ? (
        <p className="error">{ask.error.status} — {ask.error.detail}</p>
      ) : null}
      {ask.error && !(ask.error instanceof ApiError) ? (
        <p className="error">{ask.error.message}</p>
      ) : null}
      {ask.data ? (
        <section className="card">
          <h3>Answer</h3>
          <p>{ask.data.answer}</p>
          {ask.data.cited_evidence.length > 0 ? (
            <>
              <h4>Cited evidence</h4>
              <ul>
                {ask.data.cited_evidence.map((cite) => (
                  <li key={cite.evidence_id}>
                    <code>{cite.evidence_id}</code> from <code>{cite.source_uri}</code>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
