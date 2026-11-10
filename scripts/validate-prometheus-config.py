#!/usr/bin/env python3
"""Validate the rollout checksum without changing either manifest."""

import argparse
import hashlib
from pathlib import Path
import sys

import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-config", type=Path)
    args = parser.parse_args()
    base = args.root / "monitoring/prometheus"
    try:
        config = yaml.safe_load((base / "configmap.yaml").read_text(encoding="utf-8"))
        deployment = yaml.safe_load((base / "deployment.yaml").read_text(encoding="utf-8"))
        content = config["data"]["prometheus.yml"].encode("utf-8")
        expected = deployment["spec"]["template"]["metadata"]["annotations"]["checksum/config"]
        actual = hashlib.sha256(content).hexdigest()
        if expected != actual:
            print(
                "ERROR: Prometheus configuration changed without a matching rollout checksum.\n"
                f"Set Deployment spec.template.metadata.annotations checksum/config to: {actual}",
                file=sys.stderr,
            )
            return 1
        if args.output_config is not None:
            args.output_config.write_bytes(content)
    except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError) as error:
        print(f"ERROR: Invalid Prometheus manifests: {error}", file=sys.stderr)
        return 1
    print(f"Prometheus configuration checksum matches: {actual}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
