#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Manual On-Demand Ingestion Trigger
#
# Production runs automatically on schedule via EventBridge:
#   cron(16 2 ? * TUE,THU *)
#
# Prerequisite:
#   OpenTofu registers the active ECS task definition with the container image:
#   cd infra && tofu apply -var="ecr_repository_url=<account_id>.dkr.ecr.<region>.amazonaws.com/serverless-ingestion-engine"
#   Once applied in AWS, this script runs on-demand without passing any variables.
#
# Usage:
#   ./scripts/trigger_ingestion.sh            # Live on-demand run & log stream
#   ./scripts/trigger_ingestion.sh --dry-run  # Verify AWS resources without running
# ==============================================================================

AWS_REGION="${AWS_REGION:-ca-central-1}"
PROJECT_NAME="serverless-ingestion-engine"
CLUSTER_NAME="${PROJECT_NAME}-cluster"
TASK_DEF="${PROJECT_NAME}-extractor"
SG_NAME="${PROJECT_NAME}-extractor-sg"
LOG_GROUP="/ecs/${PROJECT_NAME}-extractor"
DRY_RUN=false

# Parse flags
for arg in "$@"; do
  case $arg in
    --dry-run|-d)
      DRY_RUN=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [--dry-run|-d]"
      echo ""
      echo "Options:"
      echo "  --dry-run, -d   Validate AWS resources and configuration without launching ECS task"
      echo "  --help, -h      Show this help message"
      exit 0
      ;;
  esac
done

echo "Resolving network configuration in AWS ${AWS_REGION}..."

# Fetch security group ID
SG_ID=$(aws ec2 describe-security-groups \
  --region "${AWS_REGION}" \
  --filters "Name=group-name,Values=${SG_NAME}" \
  --query "SecurityGroups[0].GroupId" \
  --output text)

if [ -z "${SG_ID}" ] || [ "${SG_ID}" = "None" ]; then
  echo "Error: Could not find Security Group ${SG_NAME}" >&2
  exit 1
fi
echo "Found Security Group: ${SG_ID}"

# Fetch VPC ID and public subnet ID
VPC_ID=$(aws ec2 describe-security-groups \
  --region "${AWS_REGION}" \
  --group-ids "${SG_ID}" \
  --query "SecurityGroups[0].VpcId" \
  --output text)

SUBNET_ID=$(aws ec2 describe-subnets \
  --region "${AWS_REGION}" \
  --filters "Name=vpc-id,Values=${VPC_ID}" "Name=map-public-ip-on-launch,Values=true" \
  --query "Subnets[0].SubnetId" \
  --output text)

if [ -z "${SUBNET_ID}" ] || [ "${SUBNET_ID}" = "None" ]; then
  SUBNET_ID=$(aws ec2 describe-subnets \
    --region "${AWS_REGION}" \
    --filters "Name=vpc-id,Values=${VPC_ID}" \
    --query "Subnets[0].SubnetId" \
    --output text)
fi
echo "Found Subnet: ${SUBNET_ID}"

# Verify cluster exists
CLUSTER_STATUS=$(aws ecs describe-clusters \
  --region "${AWS_REGION}" \
  --clusters "${CLUSTER_NAME}" \
  --query "clusters[0].status" \
  --output text)
echo "Found ECS Cluster: ${CLUSTER_NAME} (${CLUSTER_STATUS})"

# Verify task definition exists
TASK_DEF_ARN=$(aws ecs describe-task-definition \
  --region "${AWS_REGION}" \
  --task-definition "${TASK_DEF}" \
  --query "taskDefinition.taskDefinitionArn" \
  --output text)
echo "Found Task Definition: ${TASK_DEF_ARN}"

if [ "${DRY_RUN}" = true ]; then
  echo ""
  echo "================ DRY RUN SUMMARY ================"
  echo "Region:          ${AWS_REGION}"
  echo "Cluster:         ${CLUSTER_NAME} (${CLUSTER_STATUS})"
  echo "Task Definition: ${TASK_DEF_ARN}"
  echo "VPC ID:          ${VPC_ID}"
  echo "Subnet ID:       ${SUBNET_ID}"
  echo "Security Group:  ${SG_ID}"
  echo "Launch Type:     FARGATE (assignPublicIp=ENABLED)"
  echo "Log Group:       ${LOG_GROUP}"
  echo "================================================="
  echo "Dry run complete. All AWS resources verified. No task was launched."
  exit 0
fi

echo ""
echo "Triggering ephemeral ECS Fargate task: ${TASK_DEF} on cluster ${CLUSTER_NAME}..."
TASK_ARN=$(aws ecs run-task \
  --region "${AWS_REGION}" \
  --cluster "${CLUSTER_NAME}" \
  --task-definition "${TASK_DEF}" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_ID}],securityGroups=[${SG_ID}],assignPublicIp=ENABLED}" \
  --query "tasks[0].taskArn" \
  --output text)

if [ -z "${TASK_ARN}" ] || [ "${TASK_ARN}" = "None" ]; then
  echo "Error: Failed to launch ECS task." >&2
  exit 1
fi
echo "Launched task ARN: ${TASK_ARN}"
TASK_ID=$(basename "${TASK_ARN}")

echo "Waiting for task ${TASK_ID} to complete execution..."
aws ecs wait tasks-stopped \
  --region "${AWS_REGION}" \
  --cluster "${CLUSTER_NAME}" \
  --tasks "${TASK_ARN}"

echo "Task completed. Fetching container exit status..."
EXIT_CODE=$(aws ecs describe-tasks \
  --region "${AWS_REGION}" \
  --cluster "${CLUSTER_NAME}" \
  --tasks "${TASK_ARN}" \
  --query "tasks[0].containers[0].exitCode" \
  --output text)

STOP_REASON=$(aws ecs describe-tasks \
  --region "${AWS_REGION}" \
  --cluster "${CLUSTER_NAME}" \
  --tasks "${TASK_ARN}" \
  --query "tasks[0].stoppedReason" \
  --output text)

echo "Container Exit Code: ${EXIT_CODE}"
if [ "${STOP_REASON}" != "None" ]; then
  echo "Stopped Reason: ${STOP_REASON}"
fi

echo "--- Container CloudWatch Logs (${LOG_GROUP}) ---"
# CloudWatch log stream names on Fargate follow: <prefix>/<container-name>/<task-id>
STREAM_NAME="${TASK_DEF}/${TASK_DEF}/${TASK_ID}"
aws logs get-log-events \
  --region "${AWS_REGION}" \
  --log-group-name "${LOG_GROUP}" \
  --log-stream-name "${STREAM_NAME}" \
  --query "events[*].message" \
  --output text || aws logs tail "${LOG_GROUP}" --region "${AWS_REGION}" --since 5m || true

if [ "${EXIT_CODE}" != "0" ]; then
  echo "Error: ECS task failed (exit status: ${EXIT_CODE})" >&2
  if [[ "${EXIT_CODE}" =~ ^[0-9]+$ ]]; then
    exit "${EXIT_CODE}"
  else
    exit 1
  fi
fi

echo "Ingestion run succeeded."
