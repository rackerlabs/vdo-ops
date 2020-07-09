import argparse
import json
import os
import sys
from pathlib import Path

import yaml

def _no_fail_file_parse(arg):
    # Instead of throwing a system error when globbing files that don't exist, return None
    if os.path.exists(arg):
        return open(arg, 'r')


parser = argparse.ArgumentParser(
    description=(
        "Creates sam sfn definitions from our fancy yaml files"
    )
)

parser.add_argument(
    "-d", "--dir",
    dest="sam_sfn_dir",
    help="Directory of generated sam sfn definitions.",
)

parser.add_argument(
    "yaml_files",
    help="Locations of the yaml files to use.",
    type=lambda x: _no_fail_file_parse(x),
    nargs="+",
)

args = parser.parse_args()

directory = args.sam_sfn_dir
sfn_raw_directory = f"{directory}/raw"
yaml_files = args.yaml_files


def create_directory():
    print(f"Creating directory {directory} if it is necessary")

    Path(directory).mkdir(parents=True, exist_ok=True)
    Path(sfn_raw_directory).mkdir(parents=True, exist_ok=True)


def create_sfns():
    for f in yaml_files:
        if not f:
            continue
        loaded = yaml.safe_load(f, Loader=yaml.FullLoader)
        if "Definition" not in loaded.keys():
            keys_formatted = "".join(
                list(map(lambda x: f"\t- {x}\n", loaded.keys()))
            ).expandtabs(2)
            print(
                (
                    "Improper yaml format detected."
                    " This file injects yaml under a top level `Definition` block."
                    " You only have the following top level blocks defined:\n"
                    f"{keys_formatted}"
                )
            )
            sys.exit(126)
        state_definition = loaded["Definition"]

        step_states = list(filter(lambda step_state: "Parameters" in state_definition["States"][step_state],
                                  state_definition["States"]))
        for state in step_states:
            if "Input" in state_definition["States"][state]["Parameters"]:
                state_definition["States"][state]["Parameters"]["Input"]["job_id.$"] = "$.job_id"
                state_definition["States"][state]["Parameters"]["Input"]["domain.$"] = "$.domain"
            else:
                if "ParentAction" in state_definition:
                    state_definition["States"][state]["Parameters"]["parent_action"] = state_definition["ParentAction"]

                state_definition["States"][state]["Parameters"]["job_id.$"] = "$.job_id"
                state_definition["States"][state]["Parameters"]["domain.$"] = "$.domain"

        state_definition.pop('ParentAction', None)
        json_contents = json.dumps(state_definition)
        file_name = ".".join(os.path.basename(f.name).split(".")[:-1] + ["json"])

        raw_file_location = os.path.join(sfn_raw_directory, file_name)

        with open(raw_file_location, "w+") as fd:
            fd.write(json.dumps(loaded["Definition"], indent = 2))

        full_file_location = os.path.join(directory, file_name)

        contents = json.dumps({"DefinitionString": {"Fn::Sub": json_contents}})

        print(f"Generating sfn for {f.name}: {full_file_location}")

        with open(full_file_location, "w+") as fd:
            fd.write(contents)


if __name__ == "__main__":
    create_directory()
    create_sfns()