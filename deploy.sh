#! /bin/bash

STAGE=$1
SERVICE_NAME=$2
SERVICE_DIR=$3

export PATH
PATH=$(pwd)/bin:$PATH

set -e

if [ -z "${STAGE}" ]; then
  echo "Usage: ./deploy.sh <stage> <service_name> <service_directory>"
  exit 1
fi

if [ "$STAGE" == "prod" ]; then
  ENVIRONMENT="prod"
else
  ENVIRONMENT="dev"
fi

scripts/bootstrap-terraform ${ENVIRONMENT}
scripts/terraform ${STAGE} ${SERVICE_NAME} ${SERVICE_DIR}
