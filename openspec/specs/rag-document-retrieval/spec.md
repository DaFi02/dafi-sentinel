# RAG Document Retrieval Specification

> **Source**: Archived from `openspec/changes/dafi-sentinel/specs/rag-document-retrieval/spec.md` on 2026-07-14.
> Initial canonical version (no prior canonical spec existed).

## Purpose

Retrieve runbooks, documents, and evidence through staged retrieval ports, with PostgreSQL + pgvector enabled after the foundation slice.

## Requirements

### Requirement: Evidence-Cited Document Retrieval

The system MUST retrieve relevant runbooks, documents, and evidence for investigation questions and MUST return evidence references with each match.

#### Scenario: Retrieve relevant runbook

- GIVEN indexed runbooks and normalized evidence
- WHEN a user asks an incident question
- THEN retrieval returns ranked matches with evidence IDs
- AND each match includes source metadata

#### Scenario: No relevant document

- GIVEN no indexed document supports the query
- WHEN retrieval runs
- THEN the result is empty or marked unsupported
- AND no answer invents missing evidence

### Requirement: Staged pgvector Rollout

Retrieval MUST support fixture or in-memory adapters for PR1 and SHALL add PostgreSQL + pgvector behind the same port in a later slice.

#### Scenario: Foundation without database

- GIVEN only PR1 foundation dependencies are installed with `uv`
- WHEN retrieval contract tests run
- THEN they pass without PostgreSQL, pgvector, or Podman

#### Scenario: pgvector smoke enabled

- GIVEN local PostgreSQL + pgvector is started with Podman
- WHEN the pgvector adapter indexes a document embedding
- THEN similarity search returns ranked evidence references
- AND callers use the same retrieval contract
