# Delta for Investigation Workbench

## MODIFIED Requirements

### Requirement: Evidence-Cited Investigation Sessions

The system MUST let authenticated users inspect owned incident sessions, ask questions, and receive answers that cite evidence IDs. For public benchmark evidence, the workbench MUST visibly show source provenance, original trace identifier, benchmark label, and an operational-benchmark disclaimer stating that labels are not cybersecurity attack conclusions.
(Previously: Sessions exposed evidence-cited answers without public-benchmark provenance and disclaimer requirements.)

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

#### Scenario: View public benchmark evidence

- GIVEN a session contains locally prepared HDFS_v1 evidence
- WHEN an analyst views its evidence
- THEN provenance, trace identifier, label, and disclaimer are visible
