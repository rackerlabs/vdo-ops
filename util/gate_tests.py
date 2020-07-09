import os
from typing import List, Dict, Any

app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
code_root = os.path.join(app_dir, "vdo_ops")


def _build_action(actions: List[str] = [], verbosity: int = 2) -> Dict[str, Any]:
    return {"verbosity": verbosity, "actions": actions}


def _find_modules() -> List[str]:
    modules = []
    for folder_name in os.listdir(code_root):
        if not folder_name.startswith("_") and folder_name not in ["tests"]:
            modules.append(os.path.join(code_root, folder_name))
    return modules


code_dirs = " ".join(_find_modules())
test_dir = os.path.join(code_root, "tests")
sam_dir = os.path.join(app_dir, "sam")
template_file = os.path.join(sam_dir, "main.yaml")
sam_templates = []
for root, _, filenames in os.walk(sam_dir):
    for filename in filenames:
        if filename.endswith("yaml") and not "managers.yaml" in filename:
            sam_templates.append(os.path.join(root, filename))


def task_flake8() -> Dict[str, Any]:
    # line length of 88 to match black
    return _build_action(
        [
            (
                "flake8"
                " --max-line-length=88"
                " --count"
                " --statistics"
                f" {code_dirs} {test_dir}"
            )
        ]
    )

def task_black() -> Dict[str, Any]:
    return _build_action([f"black {code_dirs} {test_dir}"])


def task_bandit() -> Dict[str, Any]:
    return _build_action([f"bandit -r {code_dirs}"])


def task_pyproject_lint() -> Dict[str, Any]:
    return _build_action(["poetry check"])


def task_cfn_lint() -> Dict[str, Any]:
    # Currently E3038 is disabled because sam auto-inflates the template.
    templates_serialized = " ".join(sam_templates)
    return _build_action([f"cfn-lint -i E3038 -t {templates_serialized}"])


def task_sam_lint() -> Dict[str, Any]:
    region = os.environ.get("REGION", "us-west-2")
    template_file = os.path.join(sam_dir, "main.yaml")
    return _build_action(
        [
            (
                "sam validate"
                f" --profile vdo-ops"
                f" --region {region}"
                f" --template {template_file}"
            )
        ]
    )