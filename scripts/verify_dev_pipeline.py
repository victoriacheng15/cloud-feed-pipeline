"""Cloud Integration Test Harness for AWS Environments.

Automated verification harness for CI/CD pipelines and smoke tests:
1. Resolves VPC networking and launches an on-demand Fargate ECS task.
2. Waits for task execution and asserts exit code 0.
3. Polls DynamoDB to verify ingested records are inserted.
4. Asserts zero failed messages exist in the Dead Letter Queue (DLQ).

Usage:
    # Run verification against AWS Dev (default):
    uv run python scripts/verify_dev_pipeline.py

    # Explicit environment and region targeting:
    uv run python scripts/verify_dev_pipeline.py --environment dev --region ca-central-1
"""

import argparse
import logging
import os
import sys
import time

import boto3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("verify_pipeline")


def get_network_config(ec2_client, sg_name: str) -> tuple[str, list[str]]:
    """Resolves Security Group ID and a public Subnet ID for awsvpc task placement."""
    logger.info("Resolving security group '%s'...", sg_name)
    sg_res = ec2_client.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": [sg_name]}]
    )
    sgs = sg_res.get("SecurityGroups", [])
    if not sgs:
        raise RuntimeError(f"Could not find Security Group: {sg_name}")
    sg_id = sgs[0]["GroupId"]
    vpc_id = sgs[0]["VpcId"]

    logger.info(
        "Found Security Group %s in VPC %s. Resolving public subnets...", sg_id, vpc_id
    )
    subnet_res = ec2_client.describe_subnets(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "map-public-ip-on-launch", "Values": ["true"]},
        ]
    )
    subnets = [s["SubnetId"] for s in subnet_res.get("Subnets", [])]
    if not subnets:
        # Fallback to any subnet in the VPC
        all_subnets_res = ec2_client.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )
        subnets = [s["SubnetId"] for s in all_subnets_res.get("Subnets", [])]

    if not subnets:
        raise RuntimeError(f"No subnets found in VPC: {vpc_id}")

    logger.info("Using subnet %s and security group %s", subnets[0], sg_id)
    return sg_id, [subnets[0]]


def run_and_wait_ecs_task(
    ecs_client, cluster: str, task_def: str, sg_id: str, subnets: list[str]
) -> str:
    """Launches an on-demand Fargate task and blocks until stopped."""
    logger.info("Launching ECS Fargate task '%s' on cluster '%s'...", task_def, cluster)
    response = ecs_client.run_task(
        cluster=cluster,
        taskDefinition=task_def,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": subnets,
                "securityGroups": [sg_id],
                "assignPublicIp": "ENABLED",
            }
        },
    )
    tasks = response.get("tasks", [])
    if not tasks:
        failures = response.get("failures", [])
        raise RuntimeError(f"Failed to launch ECS task: {failures}")

    task_arn = tasks[0]["taskArn"]
    logger.info("Task launched successfully. ARN: %s", task_arn)

    logger.info("Waiting for task to complete execution...")
    waiter = ecs_client.get_waiter("tasks_stopped")
    waiter.wait(
        cluster=cluster, tasks=[task_arn], WaiterConfig={"Delay": 6, "MaxAttempts": 50}
    )

    task_desc = ecs_client.describe_tasks(cluster=cluster, tasks=[task_arn])["tasks"][0]
    container = task_desc["containers"][0]
    exit_code = container.get("exitCode")
    stopped_reason = task_desc.get("stoppedReason", "None")

    logger.info(
        "Task completed. Container exit code: %s (Reason: %s)",
        exit_code,
        stopped_reason,
    )
    if exit_code != 0:
        raise RuntimeError(
            f"ECS task exited with non-zero status code: {exit_code}. Reason: {stopped_reason}"
        )

    return task_arn


def verify_dynamodb_records(
    dynamodb_resource, table_name: str, max_wait: int = 45
) -> int:
    """Polls DynamoDB table to verify ingested article records have been inserted."""
    table = dynamodb_resource.Table(table_name)
    logger.info("Verifying DynamoDB table '%s' for processed records...", table_name)

    start_time = time.time()
    while time.time() - start_time < max_wait:
        scan_res = table.scan(Limit=10)
        items = scan_res.get("Items", [])
        if items:
            logger.info(
                "Found %d processed record(s) in DynamoDB table '%s'.",
                len(items),
                table_name,
            )
            for item in items[:3]:
                logger.info(
                    "  Sample Record: %s -> %s",
                    item.get("article_hash", "")[:12],
                    item.get("url"),
                )
            return len(items)
        logger.info("Waiting for dispatcher Lambda to write records to DynamoDB...")
        time.sleep(5)

    raise TimeoutError(
        f"No records found in DynamoDB table '{table_name}' within {max_wait}s."
    )


def verify_dead_letter_queue(sqs_client, dlq_name: str) -> None:
    """Asserts that the Dead Letter Queue contains zero failed messages."""
    logger.info("Checking Dead Letter Queue '%s'...", dlq_name)
    try:
        url_res = sqs_client.get_queue_url(QueueName=dlq_name)
        dlq_url = url_res["QueueUrl"]
    except Exception as exc:
        raise RuntimeError(f"Failed to resolve DLQ URL for {dlq_name}: {exc}") from exc

    attrs = sqs_client.get_queue_attributes(
        QueueUrl=dlq_url,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ],
    )["Attributes"]

    visible = int(attrs.get("ApproximateNumberOfMessages", "0"))
    in_flight = int(attrs.get("ApproximateNumberOfMessagesNotVisible", "0"))

    logger.info("DLQ message count: %d visible, %d in-flight", visible, in_flight)
    if visible > 0 or in_flight > 0:
        raise AssertionError(
            f"DLQ contains failed messages: {visible} visible, {in_flight} in-flight."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify AWS Dev pipeline execution.")
    parser.add_argument("--environment", "-e", default=os.getenv("ENVIRONMENT", "dev"))
    parser.add_argument(
        "--region", "-r", default=os.getenv("AWS_REGION", "ca-central-1")
    )
    parser.add_argument(
        "--project-name",
        "-p",
        default=os.getenv("PROJECT_NAME", "serverless-ingestion-engine"),
    )
    args = parser.parse_args()

    env = args.environment
    region = args.region
    project = args.project_name

    cluster_name = f"{project}-{env}-cluster"
    task_def = f"{project}-{env}-extractor"
    sg_name = f"{project}-{env}-extractor-sg"
    table_name = f"{project}-{env}"
    dlq_name = f"{project}-{env}-dlq"

    logger.info("=== Starting Cloud Pipeline Verification ===")
    logger.info("Environment:  %s", env)
    logger.info("AWS Region:   %s", region)
    logger.info("Cluster:      %s", cluster_name)
    logger.info("Task Def:     %s", task_def)
    logger.info("Table:        %s", table_name)
    logger.info("DLQ:          %s", dlq_name)
    logger.info("============================================")

    session = boto3.Session(region_name=region)
    ec2_client = session.client("ec2")
    ecs_client = session.client("ecs")
    sqs_client = session.client("sqs")
    dynamodb = session.resource("dynamodb")

    try:
        sg_id, subnets = get_network_config(ec2_client, sg_name)
        run_and_wait_ecs_task(ecs_client, cluster_name, task_def, sg_id, subnets)
        verify_dynamodb_records(dynamodb, table_name)
        verify_dead_letter_queue(sqs_client, dlq_name)
        logger.info(
            "SUCCESS: All verification checks passed for environment '%s'.", env
        )
        return 0
    except Exception:
        logger.exception("Pipeline verification failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
