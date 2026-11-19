#!/usr/bin/env python3
"""Check failure detection for Kyverno's aggregated ClusterRoles."""

from copy import deepcopy
from pathlib import Path
import runpy
import unittest

import yaml


VALIDATOR = runpy.run_path(str(Path(__file__).with_name("validate-kyverno.py")))
VALIDATE = VALIDATOR["validate_aggregation"]
ADMISSION = "kyverno:admission-controller"
EXTRA_RULE = {"apiGroups": [""], "resources": ["secrets"], "verbs": ["list"]}


class AggregationTest(unittest.TestCase):
    def setUp(self):
        self.reviewed = [
            dict(item, metadata={"name": item["name"], "labels": item.get("labels", {})})
            for item in yaml.safe_load(VALIDATOR["INVENTORY"].read_text())
            if item["kind"] == "ClusterRole"
        ]
        self.observed = {r["name"]: r for r in deepcopy(self.reviewed)}
        for role in self.observed.values():
            if "aggregationRule" in role:
                role["rules"] = deepcopy(self.observed[role["name"] + ":core"]["rules"])

    def validate(self):
        VALIDATE(self.reviewed, list(self.observed.values()), live=True)

    def test_reviewed_union(self):
        self.validate()

    def test_foreign_contributor(self):
        self.observed["foreign"] = {
            "metadata": {"name": "foreign", "labels": {"rbac.kyverno.io/aggregate-to-admission-controller": "true"}},
            "rules": [EXTRA_RULE],
        }
        with self.assertRaisesRegex(SystemExit, "unexpected contributors"):
            self.validate()

    def test_changed_core_role(self):
        self.observed[ADMISSION + ":core"]["rules"].append(EXTRA_RULE)
        with self.assertRaisesRegex(SystemExit, "rules differ from the reviewed render"):
            self.validate()

    def test_expanded_effective_rules(self):
        self.observed[ADMISSION]["rules"].append(EXTRA_RULE)
        with self.assertRaisesRegex(SystemExit, "effective rules differ"):
            self.validate()

    def test_changed_selector(self):
        self.observed[ADMISSION]["aggregationRule"]["clusterRoleSelectors"].clear()
        with self.assertRaisesRegex(SystemExit, "aggregation selectors changed"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
