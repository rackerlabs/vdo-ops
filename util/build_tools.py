import os
import toml
import subprocess
from typing import Dict, List
from pathlib import Path

stage = os.environ.get("STAGE")
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
deps_file_name = "lambda-layer-requirements.txt"
target_deps_file = os.path.join(app_dir, "build", deps_file_name)


def create_directory(directory):
    print(f"Creating directory {directory} if it is necessary")

    Path(directory).mkdir(parents=True, exist_ok=True)

def get_toml_requirements() -> List[str]:
    toml_file = os.path.join(app_dir, "pyproject.toml")
    toml_config = toml.load(toml_file)
    toml_deps = toml_config["tool"]["poetry"]["dependencies"].keys()
    deps = [k for k in toml_deps if k != "python"]
    return deps


def get_pip_requirements() -> Dict[str, str]:
    """This assumes it was generated with pip freeze, i.e, all lines are =="""
    output = subprocess.check_output("pip freeze", shell=True, text=True)
    cleaned_packages: Dict[str, str] = {}
    for row in output.split("\n"):
        if "==" not in row:
            continue
        segments = row.split("==")
        cleaned_packages[segments[0]] = segments[1]
    return cleaned_packages


def make_prod_requirements(target_file: str) -> None:
    """
    Word to the wise: Often - and _ are interchangeable.
    Also upper/lower casing must match. Watch your imports to poetry.
    """
    toml_deps = get_toml_requirements()
    pip_deps = get_pip_requirements()
    pip_keys = pip_deps.keys()
    real_deps: List[str] = []
    for d in toml_deps:
        if d in pip_keys:
            line_contents = f"{d}=={pip_deps[d]}"
            real_deps.append(line_contents.strip())
    deps_baked = os.linesep.join(real_deps)
    if len(real_deps) != len(toml_deps):
        print(
            (
                "WARNING!! You have deps defined in pyproject.toml"
                " that arent included. Check -/_ and casing!"
            )
        )
    with open(target_file, "w+") as fd:
        fd.write(deps_baked)


def poetry_wrapper() -> None:
    create_directory("build")
    make_prod_requirements(target_deps_file)


def get_last_coverage_run() -> int:
    try:
        output = subprocess.check_output(
            "coverage report", shell=True, text=True, cwd=app_dir
        )
        total_line = output.split("\n")[-2]
        total_fields = [x for x in total_line.split(" ") if x != ""]
        return int(total_fields[-1][:-1])
    except subprocess.CalledProcessError:
        return 10


def print_env_vars() -> None:
    if stage == "prod":
        response = (
            "export SubnetId1=subnet-03cb9402005d65510"
            " SubnetId2=subnet-0d928710a90b73976"
            " SecurityGroupId=sg-0fcd935acac9fd058"
        )
    else:
        response = (
            "export SubnetId1=subnet-04bf279d733ebd458"
            " SubnetId2=subnet-053850fc8130979ac"
            " SecurityGroupId=sg-011f0dac312623ade"
        )
    print(response)


def poetry_wrapper_coverage() -> None:
    print(get_last_coverage_run())
