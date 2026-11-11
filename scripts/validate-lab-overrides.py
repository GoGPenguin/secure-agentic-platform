#!/usr/bin/env python3
"""Read-only Helm/ApplicationSet checks. Requires Helm and PyYAML; no cluster API.

Compare against a captured baseline directory or an explicit Git baseline ref.
ApplicationSet checks use Helm's Go template/Sprig engine plus map merging and
list replacement for this patch subset, not a running Argo CD controller or its
Git generator/strict missing-key handling.
"""

import argparse
import copy
from pathlib import Path
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
APPS = ("frontend", "backend", "sandbox", "platform-api")
APPSET = "bootstrap/argocd/control-plane/platform-apps.yaml"
LAB = "environments/platform-api-lab-values.yaml"


def command(args, success=True):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if success:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0, "Expected validation failure: " + " ".join(map(str, args))
    return result


def render(app, base=ROOT, extra=(), success=True):
    args = ["helm", "template", app, str(base / "charts/web-app"), "-n", "gitops-apps",
            "-f", str(base / f"environments/{app}-values.yaml")]
    for path in extra:
        args.extend(["-f", str(path)])
    return command(args, success)


def container(documents):
    deployment = next(d for d in documents if d["kind"] == "Deployment")
    return deployment["spec"]["template"]["spec"]["containers"][0]


def merge_patch(target, patch):
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = copy.deepcopy(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


def appset_checks(directory, baseline):
    baseline = copy.deepcopy(baseline)
    baseline["spec"].pop("templatePatch", None)
    current = yaml.safe_load((ROOT / APPSET).read_text())
    unchanged = copy.deepcopy(current)
    unchanged["spec"].pop("templatePatch")
    assert unchanged == baseline, "Only templatePatch may change in this ApplicationSet"
    assert current["spec"]["goTemplateOptions"] == ["missingkey=error"]
    harness = directory / "template-harness"
    (harness / "templates").mkdir(parents=True)
    (harness / "Chart.yaml").write_text("apiVersion: v2\nname: validation\nversion: 0.1.0\n")
    (harness / "templates/render.yaml").write_text(
        '{{- $base := tpl (toYaml .Values.appset.spec.template) .Values.params | fromYaml -}}\n'
        '{{- $patch := tpl (.Values.appset.spec.templatePatch | default "") .Values.params -}}\n'
        '{{ dict "base" $base "patch" $patch | toJson }}\n')

    def generate(config, params, success=True):
        values = directory / "template-values.yaml"
        values.write_text(yaml.safe_dump({"appset": config, "params": params}))
        result = command(["helm", "template", "validation", str(harness), "-f", str(values)], success)
        if not success:
            assert "overrideValuesFile must be a nonempty string" in result.stderr
            return None
        rendered = yaml.safe_load(result.stdout)
        assert "Error" not in rendered["base"], rendered
        patch = yaml.safe_load(rendered["patch"]) or {}
        return merge_patch(rendered["base"], patch)

    for app in APPS:
        params = yaml.safe_load((ROOT / f"app-configs/{app}.yaml").read_text())
        assert "overrideValuesFile" not in params, "Lab support must remain inactive"
        expected = generate(baseline, params)
        assert generate(current, params) == expected, app
        activated = generate(current, {**params, "overrideValuesFile": LAB})
        with_override = copy.deepcopy(expected)
        with_override["spec"]["sources"][0]["helm"]["valueFiles"].append("$chart-repo/" + LAB)
        assert activated == with_override, "Sources, destination, identity or policy drift: " + app
    params = yaml.safe_load((ROOT / "app-configs/platform-api.yaml").read_text())
    for invalid in ("", None, True, 123, [], {}):
        generate(current, {**params, "overrideValuesFile": invalid}, success=False)
    # Untrusted newlines must remain path data, not become YAML patch instructions.
    hostile = 'missing.yaml\nspec:\n  destination:\n    namespace: other'
    generated = generate(current, {**params, "overrideValuesFile": hostile})
    assert generated["spec"]["destination"] == generate(baseline, params)["spec"]["destination"]
    assert generated["spec"]["sources"][0]["helm"]["valueFiles"][-1] == "$chart-repo/" + hostile
    print("PASS: Go/Sprig template + merge patch: four unchanged Applications; optional override preserves both sources, identity, destination and policies")
    print("PASS: invalid override values fail; JSON quoting prevents YAML patch injection")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, help="Captured <app>.yaml and platform-apps.yaml")
    parser.add_argument("--baseline-ref", default="HEAD", help="Pre-change Git ref (default HEAD)")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="lab-overrides-") as tmp:
        directory = Path(tmp)
        if args.baseline_dir:
            baselines = {app: (args.baseline_dir / f"{app}.yaml").read_text() for app in APPS}
            baseline_appset = yaml.safe_load((args.baseline_dir / "platform-apps.yaml").read_text())
        else:
            checkout = directory / "baseline"
            files = command(["git", "ls-tree", "-r", "--name-only", args.baseline_ref, "--",
                             "charts/web-app", "environments", APPSET]).stdout.splitlines()
            assert files, "Baseline Git ref contains no chart files"
            for name in files:
                target = checkout / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(command(["git", "show", f"{args.baseline_ref}:{name}"]).stdout)
            baselines = {app: render(app, checkout).stdout for app in APPS}
            baseline_appset = yaml.safe_load((checkout / APPSET).read_text())
        rendered = {}
        command(["helm", "lint", "charts/web-app"])
        for app in APPS:
            rendered[app] = render(app).stdout
            assert rendered[app] == baselines[app], "Default render drift: " + app
            assert "env" not in container(list(yaml.safe_load_all(rendered[app]))), app
            command(["helm", "lint", "charts/web-app", "-f", f"environments/{app}-values.yaml"])
        print("PASS: four default Helm renders byte-for-byte unchanged; default/per-app lint passes")

        override = yaml.safe_load((ROOT / LAB).read_text())
        base = list(yaml.safe_load_all(rendered["platform-api"]))
        active = list(yaml.safe_load_all(render("platform-api", extra=[ROOT / LAB]).stdout))
        expected = copy.deepcopy(base)
        expected_container = container(expected)
        expected_container.update({"image": f'{override["image"]["repository"]}:{override["image"]["tag"]}',
                                   "imagePullPolicy": "Never",
                                   "env": [{"name": k, "value": v} for k, v in sorted(override["env"].items())]})
        assert active == expected, "Activated render changed more than image, pull policy or env"
        assert override["image"]["digest"] == ""
        assert override["env"] == {"PLATFORM_ENVIRONMENT": "local-lab", "LAB_HTTP_503_ENABLED": "true"}
        assert override["image"]["tag"].startswith("lab-") and override["image"]["tag"] != "lab-local"
        command(["helm", "lint", "charts/web-app", "-f", "environments/platform-api-values.yaml", "-f", LAB])
        print("PASS: activated render changes only image, Never pull policy and two string env values")

        fixture = directory / "values.yaml"
        for value in (None, True, 123, 1.5, ["x"], {"x": "y"}):
            fixture.write_text(yaml.safe_dump({"env": {"TEST": value}}))
            result = render("platform-api", extra=[fixture], success=False)
            assert "string" in result.stderr and "env" in result.stderr, result.stderr
        fixture.write_text(yaml.safe_dump({"env": {"STRING_TRUE": "true", "STRING_NUMBER": "123"}}))
        env = container(list(yaml.safe_load_all(render("platform-api", extra=[fixture]).stdout)))["env"]
        assert {e["name"]: e["value"] for e in env} == {"STRING_TRUE": "true", "STRING_NUMBER": "123"}
        fixture.write_text("image:\n  tag: ignored-tag\n")
        tagged = container(list(yaml.safe_load_all(render("platform-api", extra=[fixture]).stdout)))
        assert tagged["image"] == container(base)["image"] and "@sha256:" in tagged["image"]
        missing = render("platform-api", extra=[directory / "does-not-exist.yaml"], success=False)
        assert "does-not-exist.yaml" in missing.stderr
        print("PASS: non-string env rejected; numeric/boolean-looking strings preserved; missing values file fails; production digest wins over tag")
        appset_checks(directory, baseline_appset)


if __name__ == "__main__":
    main()
