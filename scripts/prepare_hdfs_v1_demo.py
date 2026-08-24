#!/usr/bin/env python3
"""Prepare a local-only HDFS_v1 demo corpus from the official source."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from urllib.request import urlretrieve

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dafi_sentinel.ingestion.hdfs_v1 import prepare_local_demo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acknowledge-loghub-terms", action="store_true")
    parser.add_argument("--manifest", type=Path, default=Path("dafi_sentinel/ingestion/manifests/hdfs_v1.json"))
    parser.add_argument("--cache", type=Path, default=Path(".local/hdfs-v1/cache/HDFS_v1.zip"))
    parser.add_argument("--output", type=Path, default=Path(".local/hdfs-v1/output/normalized.jsonl"))
    args = parser.parse_args()
    prepare_local_demo(args.manifest, args.cache, args.output, args.acknowledge_loghub_terms, urlretrieve)


if __name__ == "__main__":
    main()
