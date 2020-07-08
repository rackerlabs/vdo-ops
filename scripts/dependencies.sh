#!/bin/bash
export PATH
PATH=$(pwd)/bin:$PATH
TERRAFORM_VERSION=0.11.14

if [[ ! -f ${PWD}/bin/terraform ]]; then
  case "$OSTYPE" in
    darwin*)  curl https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_darwin_amd64.zip -o /tmp/terraform.zip ;;
    linux*)   wget -O /tmp/terraform.zip https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip ;;
  esac
  unzip -d "${PWD}/bin" /tmp/terraform.zip
  terraform -v
fi

pip install -U pip
pip install -U awscli
pip install -U fleece[cli]
