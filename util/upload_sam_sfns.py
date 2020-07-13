import argparse
import os

import boto3

parser = argparse.ArgumentParser(
    description=(
        "Creates sam sfn definitions from our fancy yaml files"
        " and uploads them to s3 so sam can reference them."
    )
)

parser.add_argument(
    dest="sam_sfn_dir",
    help="Directory of generated sam sfn definitions.",
    type=str,
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

s3_bucket_name = f"vdo-rpcv-{args.stage}"
s3_dir = "sfns"
aws_profile_name = args.profile_name
aws_region = args.region
dir = args.sam_sfn_dir

print(f"sfns source dir: {dir}")
print(f"destination s3: {aws_region}/{s3_bucket_name}/{s3_dir}")
print(f"aws profile name: {aws_profile_name}")
print()

# We get a lot for free from environment variables
session = boto3.Session(
    profile_name=aws_profile_name, region_name=aws_region
)
s3 = session.client("s3")


def upload_sfns_to_s3():
    for file in os.listdir(dir):
        if file.endswith(".json"):
            full_path = os.path.join(dir, file)
            print(f"Uploading {full_path}")
            s3.upload_file(full_path, s3_bucket_name, f"{s3_dir}/{file}")


if __name__ == "__main__":
    upload_sfns_to_s3()
