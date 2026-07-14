# Investigation Workbench Specification

## Purpose

Provide a dashboard-owned workspace for authenticated sessions, timelines, hypotheses, evidence-cited answers, and controlled charts.

## Requirements

### Requirement: Evidence-Cited Investigation Sessions

The system MUST let authenticated users inspect owned incident sessions, ask questions, and receive answers that cite evidence IDs.

#### Scenario: User asks incident question

- GIVEN a session with normalized evidence
- WHEN the user asks why the incident started
- THEN the answer includes a concise explanation and cited evidence IDs
- AND unsupported claims are marked as unknown

#### Scenario: User sees owned session

- GIVEN a session belongs to an authenticated actor
- WHEN the workbench loads the session
- THEN the UI/API exposes the session only with the owner actor reference
- AND access decisions are auditable

#### Scenario: Evidence missing for answer

- GIVEN no evidence supports a requested conclusion
- WHEN the user asks for that conclusion
- THEN the workbench refuses to invent evidence
- AND records the unanswered question in the audit log

### Requirement: Dashboard-Owned Charts

The system MUST generate dashboard chart specifications and MUST NOT require Grafana, Prometheus, or external monitoring dashboards.

#### Scenario: Generate approved chart

- GIVEN a user requests a chart from investigation evidence
- WHEN the chart action is approved
- THEN controlled Python chart generation produces a dashboard-renderable chart artifact
- AND the chart cites the evidence used to build it

#### Scenario: Chart action denied

- GIVEN a chart request requires Python execution
- WHEN approval is denied
- THEN no Python chart generation runs
- AND the denial is visible in the session audit log
