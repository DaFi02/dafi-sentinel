# HDFS_v1 Source Verification — Local-Only Preparation Approved

**Decision:** The original release gate remains **not passed** for a committed or redistributed derivative. The approved **local-only** alternative may download from the official source after explicit acknowledgement, validate the official MD5, and write ignored local output. It MUST NOT commit, redistribute, or generate repository-tracked raw or normalized HDFS data.

**Reviewed:** 2026-08-05

## Verified primary-source record

| Claim | Authoritative source | Evidence | Status |
|---|---|---|---|
| Dataset identity | [LogHub HDFS documentation](https://raw.githubusercontent.com/logpai/loghub/master/HDFS/README.md) | Names the dataset `HDFS_v1`; describes block-ID traces and `normal`/`anomaly` ground-truth labels. | Confirmed |
| Canonical artifact | [LogHub repository index](https://raw.githubusercontent.com/logpai/loghub/master/README.md) and [Zenodo record API](https://zenodo.org/api/records/8196385) | LogHub links `HDFS_v1.zip` to Zenodo record `8196385`; the record exposes the immutable content endpoint `https://zenodo.org/api/records/8196385/files/HDFS_v1.zip/content`. | Confirmed |
| Pinned record/version | [Zenodo record API](https://zenodo.org/api/records/8196385) | Fixed DOI: `10.5281/zenodo.8196385`; publication date: 2023-07-31; record modified: 2024-01-28; API revision: 21. | Confirmed |
| Published checksum | [Zenodo record API](https://zenodo.org/api/records/8196385) | `HDFS_v1.zip` is 186,645,559 bytes with `md5:76a24b4d9a6164d543fb275f89773260`. | Confirmed (MD5 only) |
| Required LogHub notice | [LogHub LICENSE](https://raw.githubusercontent.com/logpai/loghub/master/LICENSE) | The notice says the datasets are freely available for research or academic work; any usage or distribution must refer to `https://github.com/logpai/loghub`, cite the LogHub paper where applicable, and include the license notice in all copies. | Confirmed |
| Required HDFS_v1 citations | [HDFS documentation](https://raw.githubusercontent.com/logpai/loghub/master/HDFS/README.md) and [LogHub CITATION](https://raw.githubusercontent.com/logpai/loghub/master/CITATION) | HDFS_v1 asks users to cite Xu et al., SOSP 2009 and Zhu et al., LogHub, ISSRE 2023. | Confirmed |

## Exact required notice and citations

The official LogHub license text that must be retained in any permitted copy is:

> The datasets are freely available for research or academic work, subject to the following condition: For any usage or distribution of the loghub datasets, please refer to the loghub repository URL (https://github.com/logpai/loghub) and cite the following loghub paper where applicable.
>
> Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu. Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics. In ISSRE, 2023.
>
> The above license notice shall be included in all copies of the datasets.

The HDFS_v1 documentation additionally requests:

1. Wei Xu, Ling Huang, Armando Fox, David Patterson, Michael Jordan. *Detecting Large-Scale System Problems by Mining Console Logs*. SOSP, 2009.
2. Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu. *Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics*. ISSRE, 2023.

## Release-blocking gaps

| Gate item | Finding | Why this blocks release |
|---|---|---|
| SHA-256 availability | The authoritative Zenodo record publishes only an MD5 checksum for `HDFS_v1.zip`; neither the record nor the LogHub documentation publishes a SHA-256 value. | A locally calculated SHA-256 would not establish an upstream-published checksum. The local-only workflow therefore validates the official MD5 and documents that limitation truthfully. |
| Derivative redistribution permission | Zenodo metadata labels the record `CC-BY-4.0`, while the LogHub LICENSE limits availability to research or academic work and conditions distribution on notice/citation. Neither source expressly confirms whether a normalized, committed derivative subset is permitted under the intended portfolio distribution. | The sources do not provide an unambiguous, reconciled authorization for the planned derivative/subset. Do not infer permission from the existence of a distribution condition or the Zenodo metadata label. |

## Acceptance checklist

| Required claim | Reproducible from primary source | Gate result |
|---|---|---|
| Official HDFS_v1 URL | Yes | Pass |
| Exact required notice and citation | Yes | Pass |
| Pinned source version | Yes | Pass |
| Official SHA-256 checksum | No — MD5 only | **Fail for release/redistribution; accepted for local-only validation with the official MD5** |
| Explicit derivative-redistribution permission | No — licensing statements require clarification | **Fail** |

## Enforced boundary

- Download only through the official Zenodo content endpoint, after explicit acknowledgement of LogHub terms.
- Keep raw archives, normalized output, and any local cache under ignored `.local/hdfs-v1/`; never commit or redistribute them.
- Validate the official MD5; do not claim or invent an official SHA-256.
- Do not add a starter subset. Release or derivative redistribution remains blocked until an authoritative rights holder resolves the terms and checksum questions.

## Reviewer reproduction path

1. Open the LogHub repository index and confirm its HDFS_v1 download link.
2. Open the Zenodo API record and inspect the `HDFS_v1.zip` file entry, metadata license, description, DOI, revision, and checksum.
3. Open LogHub's LICENSE and HDFS README to compare the required notice, citations, and intended research/academic framing.
4. Confirm that no source above supplies an official SHA-256 or expressly authorizes the proposed normalized derivative redistribution.
