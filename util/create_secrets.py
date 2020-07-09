from typing import Any, Generator, List, Tuple
import argparse
import yaml

import boto3


parser = argparse.ArgumentParser(description="Create docs for ssm from our secrets")
parser.add_argument(
    "secrets_file",
    metavar="secrets_file",
    help="Location of the yaml file to use.",
    type=argparse.FileType("r"),
)
parser.add_argument(
    "--region", "-r", dest="region", default="us-west-2", help="aws region"
)
parser.add_argument(
    "--stage", "-s", dest="stage", default="dev", help="Stage name (like dev or prod)"
)
parser.add_argument(
    "--profile",
    "-p",
    dest="profile_name",
    default="vdo-rpcv-dev",
    help="aws profile name (vdo-rpcv-xxx)",
)

args = parser.parse_args()

session = boto3.Session(
    profile_name=f"{args.profile_name}", region_name=args.region
)
ssm_client = session.client("ssm")

prefix = f"/rpcv/{args.stage}"


def flatten(exp: Any) -> Generator[Tuple[str, str], None, None]:
    def sub(exp: Any, res: List[str]) -> Generator[Tuple[str, Any], None, None]:
        if type(exp) == dict:
            for k, v in exp.items():
                yield from sub(v, res + [k])
        elif type(exp) == list:
            for v in exp:
                yield from sub(v, res)
        else:
            yield (f"{prefix}/{'/'.join(res)}", exp)

    yield from sub(exp, [])


data_loaded = yaml.load(args.secrets_file, Loader=yaml.FullLoader)

data_tuples = flatten(data_loaded)

new_keys = []
for dt in data_tuples:
    new_keys.append(dt[0])
    ssm_client.put_parameter(
        Name=dt[0], Value=dt[1], Type="SecureString", Overwrite=True
    )
