# ML Incident Analysis Specification

> **Source**: Archived from `openspec/changes/dafi-sentinel/specs/ml-incident-analysis/spec.md` on 2026-07-14.
> Initial canonical version (no prior canonical spec existed).

## Purpose

Provide deterministic scikit-learn anomaly scoring, clustering, similarity, and evidence ranking using stable fixtures.

## Requirements

### Requirement: Deterministic Incident Analysis

The system MUST use deterministic fixtures and configured seeds for scikit-learn anomaly, clustering, similarity, and ranking behavior.

#### Scenario: Stable anomaly scores

- GIVEN the same seeded incident fixture and model configuration
- WHEN anomaly scoring runs twice
- THEN records receive identical anomaly scores and ranking order

#### Scenario: Stable log clusters

- GIVEN a deterministic log fixture
- WHEN clustering runs twice
- THEN each log receives the same cluster label across runs

### Requirement: Evidence-Based ML Output

ML outputs MUST reference normalized evidence IDs and SHOULD expose scores suitable for dashboard review.

#### Scenario: Rank similar evidence

- GIVEN an investigation question and normalized evidence
- WHEN similarity ranking runs
- THEN the result lists evidence IDs in deterministic relevance order
- AND includes score values for reviewer inspection

#### Scenario: Fixture guards regression

- GIVEN a committed deterministic fixture with expected analysis output
- WHEN tests execute the ML analysis
- THEN deviations in scores, clusters, or ranking order fail the test
