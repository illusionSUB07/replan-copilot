#!/usr/bin/env bash
# Stop the Isaac Sim instance (compute billing ends, the disk is kept and still billed).
set -euo pipefail

: "${AWS_PROFILE:?set AWS_PROFILE}"
export AWS_PROFILE
REGION="${AWS_REGION:-eu-central-1}"
NAME=replan-copilot-isaac-sim

ids=$(aws ec2 describe-instances --region "$REGION" --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running" --query 'Reservations[].Instances[].InstanceId' --output text)
[[ -n "$ids" ]] || { echo "No running instance named $NAME in $REGION."; exit 0; }
# shellcheck disable=SC2086 # ids is a space separated list
aws ec2 stop-instances --region "$REGION" --instance-ids $ids --query 'StoppingInstances[].[InstanceId,CurrentState.Name]' --output text
