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
    bucket = "vdo-ops-terraform-state-${var.stage == "prod" ? "prod" : "dev"}"
    key    = "vdo-infrastructure/terraform.tfstate"
    region = "${var.region}"
  }
}

data "aws_iam_policy_document" "goss_role_policy_document" {
  statement {
    actions = ["lambda:InvokeFunction"]

    resources = [
      "${module.goss_create_activation_code.lambda_arn}",
      "${module.goss_vm_details.lambda_arn}", 
      "${module.goss_install_ssm_agent.lambda_arn}",
      "${module.goss_reduce_input.lambda_arn}",
      "${module.goss_patch_vms.lambda_arn}",
      "${module.goss_notifier.lambda_arn}",
      "${module.goss_set_vm_attributes.lambda_arn}",
      "${module.goss_send_command.lambda_arn}",
      "${module.goss_monitoring.lambda_arn}",
      "${module.vm_decom.lambda_arn}",
      "${module.run_process_with_output.lambda_arn}",
      "${module.run_process_with_output_azure.lambda_arn}",
      "${module.goss_user_error.lambda_arn}",
      "${module.goss_pre_checks.lambda_arn}",
      "${module.setup_ssm_agent_azure.lambda_arn}"
    ]
  }

  statement {
    actions = ["states:StartExecution", "states:DescribeExecution", "states:StopExecution"]

    resources = [
      "${aws_sfn_state_machine.goss_patching_statemachine.id}",
      "${aws_sfn_state_machine.goss_checks_statemachine.id}",
      "${aws_sfn_state_machine.setup_ssm_agent_azure_statemachine.id}",
      "${aws_sfn_state_machine.goss_unenroll_statemachine.id}",
      "${aws_sfn_state_machine.goss_monitoring_agent_install_statemachine.id}",
      "${aws_sfn_state_machine.goss_monitoring_prep_statemachine.id}",
      "${aws_sfn_state_machine.vm_decom_statemachine.id}",
      "${aws_sfn_state_machine.run_process_with_output.id}",
      "${aws_sfn_state_machine.run_process_with_output_azure.id}"
    ]
  }

  statement {
    actions = ["events:PutTargets", "events:PutRule", "events:DescribeRule"]

    resources = ["arn:aws:events:${var.region}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventsForStepFunctionsExecutionRule"]
  }

  statement {
    actions = ["iam:PassRole"]

    resources = ["${aws_iam_role.goss_role.arn}"]
  }
}

resource "aws_iam_role_policy" "goss_role_policy" {
  name = "${var.stage}-${var.service_name}-goss_lambda"

  role = "${aws_iam_role.goss_role.name}"

  policy = "${data.aws_iam_policy_document.goss_role_policy_document.json}"
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "goss_assume_role_policy_document" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type = "Service"

      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "goss_role" {
  name = "${var.stage}-${var.service_name}-goss_sfn"

  assume_role_policy = "${data.aws_iam_policy_document.goss_assume_role_policy_document.json}"
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

data "aws_iam_policy_document" "metrics_ddb_read" {
  statement {
    actions = [
      "dynamodb:BatchGet*",
      "dynamodb:DescribeLimits",
      "dynamodb:DescribeReservedCapacity*",
      "dynamodb:DescribeTable",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:DescribeStream",
      "dynamodb:Get*",
      "dynamodb:List*",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]

    resources = [
      "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/*-goss-api-metrics.v1*",
    ]
  }
}

data "aws_iam_policy_document" "tokens_ddb_read" {
  statement {
    actions = [
      "dynamodb:BatchGet*",
      "dynamodb:DescribeLimits",
      "dynamodb:DescribeReservedCapacity*",
      "dynamodb:DescribeTable",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:DescribeStream",
      "dynamodb:Get*",
      "dynamodb:List*",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]

    resources = [
      "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/*-goss-api-tokens.v1*",
    ]
  }
}

data "aws_iam_policy_document" "token_ddb_readwrite" {
  statement {
    actions = [
      "dynamodb:BatchGet*",
      "dynamodb:BatchWrite*",
      "dynamodb:DeleteItem",
      "dynamodb:DescribeLimits",
      "dynamodb:DescribeReservedCapacity*",
      "dynamodb:DescribeStream",
      "dynamodb:DescribeTable",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:Get*",
      "dynamodb:List*",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:UpdateItem",
      "dynamodb:PutItem",
    ]

    resources = [
      "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/*-goss-api-tokens.v1*",
    ]
  }
}

# Enrollment State Machine
data "template_file" "goss_statemachine_definition" {
  template = "${file("sfn/enroll-state-machine.json")}"

  vars {
    ssm_activation                  = "${module.goss_create_activation_code.lambda_arn}"
    install_ssm_agent               = "${module.goss_install_ssm_agent.lambda_function_name}"
    install_ssm_agent_arn           = "${module.goss_install_ssm_agent.lambda_arn}"
    vm_details                      = "${module.goss_vm_details.lambda_arn}"
    notifier                        = "${module.goss_notifier.lambda_arn}"
    reduce_input                    = "${module.goss_reduce_input.lambda_arn}"
    set_vm_attributes               = "${module.goss_set_vm_attributes.lambda_arn}"
    patching_sfn_arn                = "${aws_sfn_state_machine.goss_patching_statemachine.id}"
    goss_checks_sfn_arn             = "${aws_sfn_state_machine.goss_checks_statemachine.id}"
    setup_ssm_agent_azure_sfn_arn   = "${aws_sfn_state_machine.goss_checks_statemachine.id}"
    unenroll_sfn_arn                = "${aws_sfn_state_machine.goss_unenroll_statemachine.id}"
    monitoring_sfn_arn              = "${aws_sfn_state_machine.goss_monitoring_agent_install_statemachine.id}"
    monitoring_prep_sfn_arn         = "${aws_sfn_state_machine.goss_monitoring_prep_statemachine.id}"
    user_error                      = "${module.goss_user_error.lambda_arn}"
    goss_checks                     = "${module.goss_pre_checks.lambda_arn}"
    goss_checks_name                = "${module.goss_pre_checks.lambda_function_name}"
    monitoring_lambda               = "${module.goss_monitoring.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "goss_statemachine" {
  name       = "${var.stage}-${var.service_name}-enrollment"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.goss_statemachine_definition.rendered}"
}

# Azure Enrollment State Machine
data "template_file" "goss_azure_statemachine_definition" {
  template = "${file("sfn/azure-enroll-state-machine.json")}"

  vars {
    ssm_activation                  = "${module.goss_create_activation_code.lambda_arn}"
    notifier                        = "${module.goss_notifier.lambda_arn}"
    vm_details                      = "${module.goss_vm_details.lambda_arn}"
    reduce_input                    = "${module.goss_reduce_input.lambda_arn}"
    setup_ssm_azure                 = "${module.setup_ssm_agent_azure.lambda_arn}"
    patching_sfn_arn                = "${aws_sfn_state_machine.goss_patching_statemachine.id}"
    setup_ssm_agent_azure_sfn_arn   = "${aws_sfn_state_machine.setup_ssm_agent_azure_statemachine.id}"
    unenroll_sfn_arn                = "${aws_sfn_state_machine.goss_unenroll_statemachine.id}"
    monitoring_sfn_arn              = "${aws_sfn_state_machine.goss_monitoring_agent_install_statemachine.id}"
    monitoring_prep_sfn_arn         = "${aws_sfn_state_machine.goss_monitoring_prep_statemachine.id}"
    user_error                      = "${module.goss_user_error.lambda_arn}"
    monitoring_lambda               = "${module.goss_monitoring.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "goss_azure_statemachine" {
  name       = "${var.stage}-${var.service_name}-azure-enrollment"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.goss_azure_statemachine_definition.rendered}"
}

# Patch Enrollment State Machine
data "template_file" "goss_patching_statemachine_definition" {
  template = "${file("sfn/patching-state-machine.json")}"

  vars {
    patch_vms = "${module.goss_patch_vms.lambda_arn}"
    notifier  = "${module.goss_notifier.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "goss_patching_statemachine" {
  name       = "${var.stage}-${var.service_name}-patching-goss"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.goss_patching_statemachine_definition.rendered}"
}

# Setup SSM Agent Azure State Machine
data "template_file" "ssm_agent_azure_statemachine_definition" {
  template = "${file("sfn/setup_ssm_agent_azure.json")}"

  vars {
    setup_ssm_azure               = "${module.setup_ssm_agent_azure.lambda_arn}"
    notifier                      = "${module.goss_notifier.lambda_arn}"
    user_error                    = "${module.goss_user_error.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "setup_ssm_agent_azure_statemachine" {
  name       = "${var.stage}-${var.service_name}-setup-ssm-azure"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.ssm_agent_azure_statemachine_definition.rendered}"
}

# GOSS Checks State Machine
data "template_file" "goss_checks_statemachine_definition" {
  template = "${file("sfn/goss-checks-state-machine.json")}"

  vars {
    goss_checks = "${module.goss_pre_checks.lambda_arn}"
    notifier    = "${module.goss_notifier.lambda_arn}"
    user_error  = "${module.goss_user_error.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "goss_checks_statemachine" {
  name       = "${var.stage}-${var.service_name}-pre-check-goss"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.goss_checks_statemachine_definition.rendered}"
}

# GOSS Unenrollment State Machine
data "template_file" "goss_unenroll_statemachine_definition" {
  template = "${file("sfn/unenroll-state-machine.json")}"

  vars {
    ssm_activation    = "${module.goss_create_activation_code.lambda_arn}"
    install_ssm_agent = "${module.goss_install_ssm_agent.lambda_function_name}"
    vm_details        = "${module.goss_vm_details.lambda_arn}"
    notifier          = "${module.goss_notifier.lambda_arn}"
    reduce_input      = "${module.goss_reduce_input.lambda_arn}"
    set_vm_attributes = "${module.goss_set_vm_attributes.lambda_arn}"
    send_command      = "${module.goss_send_command.lambda_arn}"
    patch_vms         = "${module.goss_patch_vms.lambda_arn}"
  }
}

# AWS GOSS setup State Machine
data "template_file" "goss_aws_setup_statemachine_definition" {
  template = "${file("sfn/aws-goss-setup.json")}"

  vars {
    patch_vms = "${module.goss_patch_vms.lambda_arn}"
    notifier    = "${module.goss_notifier.lambda_arn}"
    user_error  = "${module.goss_user_error.lambda_arn}"
    monitoring_prep_sfn_arn  = "${aws_sfn_state_machine.goss_monitoring_prep_statemachine.id}"
  }
}

resource "aws_sfn_state_machine" "goss_aws_setup_statemachine" {
  name       = "${var.stage}-${var.service_name}-aws-setup-goss"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.goss_aws_setup_statemachine_definition.rendered}"
}

resource "aws_sfn_state_machine" "goss_unenroll_statemachine" {
  name       = "${var.stage}-${var.service_name}-unenroll-goss"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.goss_unenroll_statemachine_definition.rendered}"
}

# Modules
module "goss_create_activation_code" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-goss-create-activation-code"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "ssm_activation.handler"
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

resource "aws_iam_role_policy" "goss_ssm_activation_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-ssm-activation"
  role   = "${module.goss_create_activation_code.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

# VM Details

module "goss_vm_details" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-vm-details"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "gather_vm_details.handler"
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

resource "aws_iam_role_policy" "goss_vm_details_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-vm-details_ssm"
  role   = "${module.goss_vm_details.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

# Reduce Input from Parallel Steps
module "goss_reduce_input" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-lambda-creation"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 120
  runtime      = "python3.6"
  handler      = "reduce_input.handler"
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

  #VPC Configuration
  subnet_ids         = ["${data.terraform_remote_state.vdo_infra.private_subnets}"]
  security_group_ids = ["${data.terraform_remote_state.vdo_infra.default_security_group_id}"]
}

resource "aws_iam_role_policy" "goss_reduce_input_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-lambda-creation"
  role   = "${module.goss_reduce_input.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

module "goss_install_ssm_agent" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-goss-install-ssm-agent"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "install_ssm_agent.handler"
  tracing_mode = "Active"

  env_variables = {
    LOG_LEVEL       = "${var.stage == "prod" ? "INFO" : "DEBUG"}"
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

# Patch VMs
module "goss_patch_vms" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-patch-vms"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 120
  runtime      = "python3.6"
  handler      = "patch_vms.handler"
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

  #VPC Configuration
  subnet_ids         = ["${data.terraform_remote_state.vdo_infra.private_subnets}"]
  security_group_ids = ["${data.terraform_remote_state.vdo_infra.default_security_group_id}"]
}

resource "aws_iam_role_policy" "goss_patch_vms_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-patch-vms"
  role   = "${module.goss_patch_vms.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

# Send Commands
module "goss_send_command" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-send-command"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 300
  runtime      = "python3.6"
  handler      = "send_command.handler"
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

  #VPC Configuration
  subnet_ids         = ["${data.terraform_remote_state.vdo_infra.private_subnets}"]
  security_group_ids = ["${data.terraform_remote_state.vdo_infra.default_security_group_id}"]
}

resource "aws_iam_role_policy" "goss_send_command_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-send-command"
  role   = "${module.goss_send_command.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

module "goss_notifier" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-notifier"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "notifier.handler"
  tracing_mode = "Active"

  env_variables = {
    LOG_LEVEL       = "${var.stage == "prod" ? "INFO" : "DEBUG"}"
    SSM_PARAMS_PATH = "/vdo/global"
    STAGE           = "${var.stage}"
    TICKET_SIMULATION_MODE = true
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

resource "aws_iam_role_policy" "goss_notifier_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-notifier"
  role   = "${module.goss_notifier.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

# ssmid Registration/set vm attributes

module "goss_set_vm_attributes" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-set_vm_attributes"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "set_vm_attributes.handler"
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

resource "aws_iam_role_policy" "goss_set_vm_attributes_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-set_vm_attributes_ssm"
  role   = "${module.goss_set_vm_attributes.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

# goss monitoring
module "goss_monitoring" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-monitoring"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "monitoring.handler"
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

resource "aws_iam_role_policy" "goss_monitoring_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-monitoring_ssm"
  role   = "${module.goss_monitoring.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

resource "aws_iam_role_policy" "goss_monitoring_metrics_ddb_read_policy" {
  name   = "${var.stage}_vmc-${var.service_name}-get_metrics-ddb-read"
  role   = "${module.goss_monitoring.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.metrics_ddb_read.json}"
}

resource "aws_iam_role_policy" "goss_monitoring_tokens_ddb_read_policy" {
  name   = "${var.stage}_vmc-${var.service_name}-get_tokens-ddb-read"
  role   = "${module.goss_monitoring.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.tokens_ddb_read.json}"
}

resource "aws_iam_role_policy" "goss_monitoring_tokens_ddb_readwrite_policy" {
  name   = "${var.stage}_vmc-${var.service_name}-get_tokens-ddb-readwrite"
  role   = "${module.goss_monitoring.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.token_ddb_readwrite.json}"
}

data "template_file" "goss_monitoring_prep_statemachine_definition" {
  template = "${file("sfn/monitoring-prep-state-machine.json")}"

  vars {
    monitoring_lambda = "${module.goss_monitoring.lambda_arn}"
    notifier          = "${module.goss_notifier.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "goss_monitoring_prep_statemachine" {
  name       = "${var.stage}-${var.service_name}-monitoring-prep"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.goss_monitoring_prep_statemachine_definition.rendered}"
}

data "template_file" "goss_monitoring_agent_install_statemachine_definition" {
  template = "${file("sfn/monitoring-agent-install-state-machine.json")}"

  vars {
    monitoring_lambda = "${module.goss_monitoring.lambda_arn}"
    notifier          = "${module.goss_notifier.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "goss_monitoring_agent_install_statemachine" {
  name       = "${var.stage}-${var.service_name}-monitoring-agent-install"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.goss_monitoring_agent_install_statemachine_definition.rendered}"
}

# VM decom
module "vm_decom" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-vm-decom"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "vm_decom.handler"
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

data "aws_iam_policy_document" "vm_decom_ssm" {
  statement {
    actions = [
      "ssm:GetInventory",
      "ssm:DescribeInstanceInformation",
      "ssm:DeregisterManagedInstance"
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "vm_decom_policy" {
  name   = "${var.stage}-${var.service_name}-vm-decom"
  role   = "${module.vm_decom.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.vm_decom_ssm.json}"
}

resource "aws_iam_role_policy" "vm_decom_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-vm-decom-ssm-read"
  role   = "${module.vm_decom.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

data "template_file" "vm_decom_statemachine_definition" {
  template = "${file("sfn/vm-decom-state-machine.json")}"

  vars {
    vm_decom_lambda   = "${module.vm_decom.lambda_arn}"
    monitoring_lambda = "${module.goss_monitoring.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "vm_decom_statemachine" {
  name       = "${var.stage}-${var.service_name}-vm-decom"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.vm_decom_statemachine_definition.rendered}"
}

# Run process with output
module "run_process_with_output" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-run-process-with-output"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "run_process_with_output.handler"
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

resource "aws_iam_role_policy" "run_process_with_output_ssm_read" {
  name   = "${var.stage}-${var.service_name}-ssm-read"
  role   = "${module.run_process_with_output.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

data "template_file" "run_process_with_output" {
  template = "${file("sfn/run_process_with_output.json")}"

  vars {
    lambda = "${module.run_process_with_output.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "run_process_with_output" {
  name       = "${var.stage}-${var.service_name}-run-process-with-output"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.run_process_with_output.rendered}"
}

data "aws_iam_policy_document" "goss_caller_sfn_policy" {
  statement {
    actions = [
      "states:StartExecution",
      "states:DescribeExecution",
      "states:StopExecution",
    ]

    resources = [
      "${aws_sfn_state_machine.run_process_with_output.id}",
      "${aws_sfn_state_machine.run_process_with_output_azure.id}"
    ]
  }
}

resource "aws_iam_role_policy" "goss_ssm_installer_sfn_policy" {
  name   = "${var.stage}-${var.service_name}-goss_ssm_install_lambda_sfn"
  role   = "${module.goss_install_ssm_agent.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.goss_caller_sfn_policy.json}"
}

resource "aws_iam_role_policy" "goss_checks_sfn_policy" {
  name   = "${var.stage}-${var.service_name}-goss_checks_lambda_sfn"
  role   = "${module.goss_pre_checks.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.goss_caller_sfn_policy.json}"
}

resource "aws_iam_role_policy" "setup_ssm_azure_sfn_policy" {
  name   = "${var.stage}-${var.service_name}-setup_ssm_azure_lambda_sfn"
  role   = "${module.setup_ssm_agent_azure.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.goss_caller_sfn_policy.json}"
}


# Run process with output for Azure
module "run_process_with_output_azure" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-run-process-with-output-azure"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "run_process_with_output_azure.handler"
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

resource "aws_iam_role_policy" "run_process_with_output_azure_ssm_read" {
  name   = "${var.stage}-${var.service_name}-ssm-read-azure"
  role   = "${module.run_process_with_output_azure.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}

data "template_file" "run_process_with_output_azure" {
  template = "${file("sfn/run_process_with_output_azure.json")}"

  vars {
    lambda = "${module.run_process_with_output_azure.lambda_arn}"
  }
}

resource "aws_sfn_state_machine" "run_process_with_output_azure" {
  name       = "${var.stage}-${var.service_name}-run-process-with-output-azure"
  role_arn   = "${aws_iam_role.goss_role.arn}"
  definition = "${data.template_file.run_process_with_output_azure.rendered}"
}


# GOSS user error
module "goss_user_error" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-user-error"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "user_error.handler"
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

# GOSS Checks
module "goss_pre_checks" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-goss-checks"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "goss_checks.handler"
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


# Setup SSM Agent Azure
module "setup_ssm_agent_azure" {
  source       = "github.com/rackerlabs/xplat-terraform-modules//modules/lambda-in-vpc"
  name         = "${var.service_name}-setup-ssm-azure"
  stage        = "${var.stage}"
  file         = "./dist/lambda_function.zip"
  memory_size  = 256
  timeout      = 60
  runtime      = "python3.6"
  handler      = "setup_ssm_azure.handler"
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

resource "aws_iam_role_policy" "setup_ssm_azure_ssm_read_policy" {
  name   = "${var.stage}-${var.service_name}-ssm-setup-azure"
  role   = "${module.setup_ssm_agent_azure.lambda_role_name}"
  policy = "${data.aws_iam_policy_document.ssm_read.json}"
}