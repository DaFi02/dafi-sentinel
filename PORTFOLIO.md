# DAFI Sentinel: Project Portfolio

DAFI Sentinel is a security-first incident investigation workbench. It helps an analyst turn a small, local incident dataset into a traceable investigation: evidence, findings, questions, charts, and an audit trail.

## The problem it addresses

Investigating an incident is difficult when logs, alerts, deployment events, and operational context are disconnected. It is also risky to let an AI system act on untrusted incident text without controls.

DAFI Sentinel explores a safer approach: every conclusion must be tied to evidence, sensitive values are redacted, access is scoped to the user, and controlled actions require approval.

## What it does

1. Ingests local incident fixtures such as logs, alerts, deployments, and metric-like tables.
2. Normalizes them into stable, timestamped evidence records.
3. Redacts sensitive values before downstream analysis.
4. Analyzes evidence with deterministic ML for anomaly detection, log clustering, and similarity ranking.
5. Lets authenticated users inspect their evidence and ask evidence-cited questions.
6. Produces validated charts from approved evidence.
7. Records security decisions and user actions in an audit log.
8. Orchestrates an investigation flow with LangGraph and pauses for human approval before chart rendering.

## Example investigation flow

An analyst opens an incident session and reviews normalized evidence. They ask why an incident started; the workbench responds only with evidence IDs that support the answer. The analyst can request a chart around an anomaly, but the orchestration flow pauses until an authorized human approves it. The request, decision, and result are recorded in the audit trail.

## What this project demonstrates

| Area | Implementation |
|---|---|
| Security-first AI | Prompt-boundary checks, redaction, scoped permissions, approvals, and audits. |
| Explainable analysis | Evidence IDs back answers and chart requests; unsupported conclusions are refused. |
| Applied ML | Deterministic scikit-learn anomaly scoring, clustering, and similarity ranking. |
| Full-stack delivery | FastAPI backend plus React, TypeScript, and Vite dashboard. |
| Agent orchestration | A small LangGraph state machine keeps orchestration separate from business logic. |
| Quality practices | Automated backend and frontend tests, explicit specifications, and controlled local infrastructure. |

## Scope and boundaries

This is a local, portfolio-grade V1. It intentionally does not connect to live cloud logs, SIEMs, ticketing platforms, or perform automatic remediation. The goal is to prove a safe, explainable investigation workflow before adding operational integrations.

## Optional HDFS_v1 provenance demo

The portfolio also includes an optional, local-only [LogHub HDFS_v1](https://github.com/logpai/loghub/tree/master/HDFS) walkthrough. It demonstrates provenance rather than a claim of real cyberattack detection: the source `Normal` and `Anomaly` labels are operational benchmark metadata, **not cybersecurity attack conclusions**.

- **Official source:** pinned Zenodo artifact `https://zenodo.org/api/records/8196385/files/HDFS_v1.zip/content` (DOI `10.5281/zenodo.8196385`), with the LogHub notice and the HDFS-requested Xu et al. (SOSP 2009) and Zhu et al. (ISSRE 2023) citations.
- **Explicit local preparation:** `uv run python scripts/prepare_hdfs_v1_demo.py --acknowledge-loghub-terms` downloads only after acknowledgement and writes ignored local output.
- **Integrity limit:** the official record publishes `md5:76a24b4d9a6164d543fb275f89773260`. No official SHA-256 is published, so this project does not present a locally calculated hash as official truth.
- **No redistribution:** raw and normalized corpus files are **not committed or redistributed**; no starter subset is included because derivative redistribution permission remains unresolved.
- **Reviewer-visible provenance:** set `DAFI_HDFS_DEMO_PATH` to the prepared `.local/hdfs-v1/output/normalized.jsonl`, run the development API, then open an evidence detail. `GET /evidence/{id}` and the dashboard display the source URI, version/checksum reference, original trace ID, benchmark label, and disclaimer.

### Deterministic sample boundary

The optional local sample contains at most **10 traces per label**, selected after sorting first by label (`Anomaly` then `Normal`) and then by trace ID; it is emitted in that same order. This small deterministic slice exists to demonstrate provenance and repeatable analysis inputs. It is **not statistically representative** of HDFS_v1, production workloads, incident prevalence, or cybersecurity attacks.

This is reproducible local preparation, not model training. The existing deterministic analysis runs over the prepared evidence; the project does not train or ship a model from HDFS_v1.

## My contribution and AI use

I conceived the product direction, selected the problem to solve, defined the scope and priorities, and reviewed the behavior and technical decisions. I used AI as an engineering assistant to accelerate research, implementation, testing, and documentation.

The project should be presented honestly as **an AI-assisted project built and directed by Diego Andia Fernandez**. AI assistance does not replace ownership: the portfolio value is in the product framing, architecture choices, security constraints, validation, and ability to explain the tradeoffs.

## Run it locally

```bash
uv sync
uv run pytest
uv run uvicorn dafi_sentinel.api.app:default_workbench_app --reload
```

For the dashboard:

```bash
cd frontend
npm install
npm run dev
```

See [README.md](README.md) for API details, development credentials, optional pgvector testing, and the full setup guide.
