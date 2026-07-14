import { FormEvent, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";

import { useRenderChart } from "../api/queries";
import { ApiError, type ChartSpecPayload } from "../api/client";

const SAMPLE_DATA: Array<[number, number]> = [
  [0, 120],
  [1, 145],
  [2, 200],
  [3, 165],
  [4, 95],
];

const DEFAULT_SPEC: ChartSpecPayload = {
  kind: "line",
  title: "Latency over time",
  x: "minute",
  y: "ms",
  evidence_ids: ["ev-incident-001"],
};

export function ChartsPage() {
  const [spec, setSpec] = useState<ChartSpecPayload>(DEFAULT_SPEC);
  const render = useRenderChart(true);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    render.reset();
    try {
      await render.mutateAsync({ spec, data: SAMPLE_DATA });
    } catch {
      // surfaced via render.error
    }
  };

  return (
    <main>
      <h2>Render a chart</h2>
      <form onSubmit={(event) => void onSubmit(event)}>
        <label htmlFor="chart-kind">kind</label>
        <select
          id="chart-kind"
          className="input"
          value={spec.kind}
          onChange={(event) => setSpec({ ...spec, kind: event.target.value as ChartSpecPayload["kind"] })}
        >
          <option value="line">line</option>
          <option value="bar">bar</option>
          <option value="scatter">scatter</option>
          <option value="table">table</option>
        </select>
        <label htmlFor="chart-title">title</label>
        <input
          id="chart-title"
          className="input"
          value={spec.title}
          onChange={(event) => setSpec({ ...spec, title: event.target.value })}
        />
        <label htmlFor="chart-x">x axis</label>
        <input
          id="chart-x"
          className="input"
          value={spec.x}
          onChange={(event) => setSpec({ ...spec, x: event.target.value })}
        />
        <label htmlFor="chart-y">y axis</label>
        <input
          id="chart-y"
          className="input"
          value={spec.y}
          onChange={(event) => setSpec({ ...spec, y: event.target.value })}
        />
        <label htmlFor="chart-evidence">evidence ids (comma separated)</label>
        <input
          id="chart-evidence"
          className="input"
          value={spec.evidence_ids.join(",")}
          onChange={(event) =>
            setSpec({ ...spec, evidence_ids: event.target.value.split(",").map((s) => s.trim()).filter(Boolean) })
          }
        />
        <button className="button" type="submit" disabled={render.isPending}>
          {render.isPending ? "rendering…" : "render"}
        </button>
      </form>

      {render.error instanceof ApiError ? (
        <p className="error">{render.error.status} — {render.error.detail}</p>
      ) : null}

      {render.data ? (
        <section className="card">
          <h3>{render.data.spec.title}</h3>
          <div className="chart-frame" data-testid="recharts-shell">
            <ResponsiveContainer width="100%" height={300}>
              {render.data.spec.kind === "bar" ? (
                <BarChart data={SAMPLE_DATA.map(([x, y]) => ({ x, y }))}>
                  <CartesianGrid stroke="#e1e4e8" />
                  <XAxis dataKey="x" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="y" fill="#1f6feb" />
                </BarChart>
              ) : render.data.spec.kind === "scatter" ? (
                <ScatterChart>
                  <CartesianGrid stroke="#e1e4e8" />
                  <XAxis dataKey="x" type="number" />
                  <YAxis dataKey="y" type="number" />
                  <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                  <Scatter data={SAMPLE_DATA.map(([x, y]) => ({ x, y }))} fill="#1f6feb" />
                </ScatterChart>
              ) : (
                <LineChart data={SAMPLE_DATA.map(([x, y]) => ({ x, y }))}>
                  <CartesianGrid stroke="#e1e4e8" />
                  <XAxis dataKey="x" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="y" stroke="#1f6feb" />
                </LineChart>
              )}
            </ResponsiveContainer>
          </div>
          <p className="muted">cites {render.data.cited_evidence.length} evidence id(s)</p>
        </section>
      ) : null}
    </main>
  );
}
