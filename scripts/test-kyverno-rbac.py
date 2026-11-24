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
REPORTS = VALIDATOR["REPORTS_AGGREGATE"]
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

    def test_reporting_extension_effective_union(self):
        role = yaml.safe_load(VALIDATOR["REPORTING_ROLE"].read_text())
        self.observed[role["metadata"]["name"]] = role
        self.observed[REPORTS]["rules"] += deepcopy(role["rules"])
        VALIDATE(self.reviewed, list(self.observed.values()), live=True, reporting_role=role)
        self.observed[REPORTS]["rules"].pop()
        with self.assertRaisesRegex(SystemExit, "effective rules differ"):
            VALIDATE(self.reviewed, list(self.observed.values()), live=True, reporting_role=role)


class ReportingRoleTest(unittest.TestCase):
    def setUp(self):
        self.role = yaml.safe_load(VALIDATOR["REPORTING_ROLE"].read_text())
        directory = VALIDATOR["REPORTING_BOOTSTRAP"]
        self.project = yaml.safe_load((directory / "project.yaml").read_text())
        self.app = yaml.safe_load((directory / "application.yaml").read_text())

    def validate(self):
        VALIDATOR["validate_reporting_rbac"](self.role, self.project, self.app)

    def test_reviewed_manifests(self):
        self.validate()

    def test_each_required_permission(self):
        for verb in ("get", "list", "watch"):
            with self.subTest(verb=verb):
                self.role["rules"][0]["verbs"] = [v for v in ("get", "list", "watch") if v != verb]
                with self.assertRaisesRegex(SystemExit, "must grant only"):
                    self.validate()

    def test_reject_unrelated_access(self):
        for key, value in (("verbs", "update"), ("resources", "secrets"), ("resources", "*")):
            with self.subTest(key=key, value=value):
                rule = self.role["rules"][0]
                rule[key].append(value)
                with self.assertRaisesRegex(SystemExit, "must grant only"):
                    self.validate()
                rule[key].pop()

    def test_reject_wider_project(self):
        self.project["spec"]["clusterResourceWhitelist"].append(
            {"group": "rbac.authorization.k8s.io", "kind": "ClusterRoleBinding"}
        )
        with self.assertRaisesRegex(SystemExit, "AppProject must permit only ClusterRole"):
            self.validate()

    def test_reject_automation(self):
        self.app["spec"]["syncPolicy"]["automated"] = {"enabled": True}
        with self.assertRaisesRegex(SystemExit, "Application must be manual"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
