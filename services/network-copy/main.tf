variable "region" {}

variable "stage" {}

variable "service_name" {}

variable "alarm_topic_names" {
  type = "list"

  default = []
}

variable "alarm_topic_arns" {
  type = "list"

  default = []
}

terraform {
  backend "s3" {
    encrypt = true

    acl = "private"

    region = "us-west-2"
  }
}

provider "aws" {
  region = "${var.region}"
}

data "terraform_remote_state" "vdo_infra" {
  backend = "s3"

  config {
    bucket = "vdo-terraform-state-${var.stage == "prod" ? "prod" : "dev"}"
    key    = "vdo-infrastructure/terraform.tfstate"
    region = "${var.region}"
  }
}

data "aws_iam_policy_document" "vdo_ops_role_policy_document" {
  statement {
    actions = ["lambda:InvokeFunction"]

    resources = [
      "${module.vdo_ops_network_copy.lambda_arn}"
    ]
  }

  statement {
    actions = ["iam:PassRole"]

    resources = ["${aws_iam_role.vdo_ops_role.arn}"]
  }
}

resource "aws_iam_role_policy" "vdo_ops_role_policy" {
  name = "${var.stage}-${var.service_name}-vdo-ops_lambda"

  role = "${aws_iam_role.vdo_ops_role.name}"

  policy = "${data.aws_iam_policy_document.vdo_ops_role_policy_document.json}"
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "vdo_ops_assume_role_policy_document" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type = "Service"

      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "vdo_ops_role" {
  name = "${var.stage}-${var.service_name}-vdo-ops_sfn"

  assume_role_policy = "${data.aws_iam_policy_document.vdo_ops_assume_role_policy_document.json}"
}


data "aws_iam_policy_document" "ssm_read" {
  statement {
    actions = [
      "ssm:DescribeParam*",
      "ssm:GetParam*",
      "kms:Decrypt",
    ]

    # We can scope the SSM params down after we figure out what the namespace
    # will be.
    resources = [
      "${data.terraform_remote_state.vdo_infra.vdo_secrets_kms_key_arn}",
      "arn:aws:ssm:*:*:parameter/*",
    ]
  }
}

# Modules
module "vdo_ops_network_copy" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-network-copy"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "network_copy.handler"
  tracing_mode = "Active"

  env_variables = {
    LOG_LEVEL       = "${var.stage == "prod" ? "INFO" : "DEBUG"}"
    SSM_PARAMS_PATH = "/vdo/global"
    STAGE           = "${var.stage}"
  }

  enable_monitoring = "${var.stage == "prod" ? 1 : 0}"

  # If there are alarm_topic_names and/or alarm_topic_arns, iterate through
  # the names and format them, then combine with ARNs. This allows you to
  # manually specify ARNs across accounts and/or specify local topics.
  alarm_actions = "${concat(var.alarm_topic_arns, formatlist("arn:aws:sns:%s:%s:%s", var.region, data.aws_caller_identity.current.account_id, var.alarm_topic_names))}"

  # VPC Configuration
  subnet_ids         = ["${data.terraform_remote_state.vdo_infra.private_subnets}"]
  security_group_ids = ["${data.terraform_remote_state.vdo_infra.default_security_group_id}"]
}

resource "aws_iam_role_policy" "vdo_ops_network_copy_read_policy" {
  name   = "${var.stage}-${var.service_name}-network-copy"
  role   = "${module.vdo_ops_network_copy.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}