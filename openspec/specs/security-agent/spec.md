# Security Agent Specification

> **Source**: Archived from `openspec/changes/dafi-sentinel/specs/security-agent/spec.md` on 2026-07-14.
> Initial canonical version (no prior canonical spec existed).

## Purpose

Enforce prompt boundaries, redaction, identity-aware authorization, permissions, approvals, and auditability for agent-assisted investigations.

## Requirements

### Requirement: Prompt Boundary Enforcement

The Security Agent MUST treat incident data and user input as untrusted and MUST prevent prompt-injection text from changing tool policy or disclosure rules.

#### Scenario: Prompt injection in log content

- GIVEN evidence text contains instructions to ignore security policy
- WHEN the agent analyzes the evidence
- THEN the instruction is treated as data only
- AND no restricted tool or disclosure policy is changed

#### Scenario: User requests policy bypass

- GIVEN a user asks the agent to reveal unredacted secrets
- WHEN the request is evaluated
- THEN the Security Agent refuses the request
- AND cites the applicable permission boundary

### Requirement: Redaction, Permissions, and Audit Logs

The Security Agent MUST redact sensitive values, enforce actor role/tool permissions, require approval for controlled Python execution, and audit security decisions.

#### Scenario: Sensitive value redaction

- GIVEN evidence contains tokens, credentials, or personal identifiers
- WHEN evidence is shown or sent to an agent
- THEN sensitive values are replaced with stable redaction markers

#### Scenario: Unauthorized tool call

- GIVEN an agent requests a tool outside its permission scope
- WHEN the Security Agent evaluates the request
- THEN the tool call is denied
- AND an audit log records actor, action, reason, role context, and timestamp

### Requirement: Authenticated Actor Attribution

The system MUST model authenticated actors for session ownership, approvals, and audit attribution, while PR1 MUST NOT implement login or session middleware.

#### Scenario: Actor owns investigation session

- GIVEN an authenticated user actor opens an investigation session
- WHEN a question, approval, or tool request is recorded
- THEN the record includes the actor reference and session owner

#### Scenario: PR1 auth scope stays contractual

- GIVEN the foundation slice is being implemented
- WHEN auth-related models are added
- THEN only `ActorRef`, `UserRef`, `Role`, and `Permission` contracts are required
- AND no login, token validation, or SSO flow is implemented
