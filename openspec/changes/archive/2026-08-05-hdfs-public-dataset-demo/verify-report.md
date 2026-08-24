## Verification Report

**Change**: hdfs-public-dataset-demo  
**Mode**: Hybrid persistence; Strict TDD; fresh-context final re-verification  
**Verdict**: PASS WITH WARNINGS — archive-ready for the approved local-only scope; it remains ineligible for corpus/subset release or redistribution.

### Completeness
| Metric | Value |
|---|---:|
| Planned numbered tasks | 12 |
| Complete | 12 |
| Incomplete | 0 |

The PR 0 checksum/derivative-rights gate is intentionally blocked and documented; it is not an unchecked implementation task and the implemented scope correctly remains local-only.

### Runtime evidence
| Command | Result |
|---|---|
| `uv run pytest tests/dafi_sentinel/test_hdfs_v1.py::test_preparation_rejects_missing_or_blank_benchmark_label_without_output -vv` | 2 passed |
| `uv run pytest tests/dafi_sentinel/test_hdfs_v1.py -q` | 10 passed |
| `uv run pytest tests/dafi_sentinel/test_hdfs_v1_release_proof.py tests/dafi_sentinel/test_api_endpoints.py -q` | 38 passed; 2 dependency deprecation warnings |
| `uv run pytest` | 254 passed, 1 skipped (opt-in pgvector), 5 xpassed, 18 existing/dependency warnings |
| `frontend: npm test -- --run` | 33 passed |
| `frontend: npm run build` | Passed; Vite warns of a >500 kB minified chunk |
| `git diff --check` | Clean |
| tracked/history HDFS corpus scan | No output |

### Compliance summary

All 5 specified scenarios are compliant. Acknowledgement-before-I/O, validated deterministic local preparation, provenance retention, and analyst-visible benchmark framing are covered by backend and frontend tests. No critical issues remain.

### Warnings and retained gate

1. No official SHA-256 and no unambiguous permission to redistribute a normalized derivative are available from the primary sources. This blocks committed corpus/subsets, redistribution, and related release claims. The only approved scope is local preparation under ignored `.local/hdfs-v1/`, validated against the official MD5 after explicit acknowledgement.
2. The frontend production build emits an existing >500 kB Vite chunk warning. It does not affect correctness or archive eligibility.
3. Existing/dependency deprecations and expected xpasses remain in test output; none failed.

### Archive readiness

Ready to archive only if the local-only boundary and legal/data gate remain explicit. Archival does not grant permission to commit or redistribute HDFS corpus data.
