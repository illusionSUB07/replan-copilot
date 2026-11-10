#!/usr/bin/env bash
# Terminate the Isaac Sim instance (disk is deleted with it) and delete its security group.
set -euo pipefail

: "${AWS_PROFILE:?set AWS_PROFILE}"
export AWS_PROFILE
REGION="${AWS_REGION:-eu-central-1}"
NAME=replan-copilot-isaac-sim
aws() { command aws --region "$REGION" "$@"; }

ids=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" --query 'Reservations[].Instances[].InstanceId' --output text)
sgs=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" --query 'SecurityGroups[].GroupId' --output text)
echo "Will terminate: ${ids:-none}; delete security group: ${sgs:-none}"
read -r -p "Type 'yes' to destroy: " answer
[[ "$answer" == yes ]] || { echo "Aborted."; exit 1; }

if [[ -n "$ids" ]]; then
  # shellcheck disable=SC2086 # ids is a space separated list
  aws ec2 terminate-instances --instance-ids $ids >/dev/null
  # shellcheck disable=SC2086
  aws ec2 wait instance-terminated --instance-ids $ids
fi
for sg in $sgs; do aws ec2 delete-security-group --group-id "$sg"; done
echo "Destroyed."
