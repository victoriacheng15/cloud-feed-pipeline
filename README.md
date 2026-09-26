# Cloud Feed Pipeline

Cloud Feed Pipeline is an automated, serverless event-driven ingestion and notification pipeline built with Python, OpenTofu, ECS Fargate, SNS, SQS, Lambda, DynamoDB, and Discord Webhooks.

It proves an end-to-end cloud platform ownership loop: scheduled serverless compute extracts and normalizes RSS feeds, decoupled pub/sub messaging buffers delivery bursts, a check-first database layer guarantees idempotent notifications, and GitHub Actions OIDC automates zero-credential deployments with zero fixed idle infrastructure.

## Architecture

The system processes requests and manages state through simplified operational paths:

| Path | Purpose | Flow |
| :--- | :--- | :--- |
| **Scheduled Extraction** | Parse feeds concurrently in public subnets with zero NAT Gateways | EventBridge -> ECS Fargate -> S3 |
| **Decoupled Fan-Out** | Buffer feed bursts and isolate third-party rate limits | ECS Extractor -> SNS Topic -> SQS Queue |
| **Poison-Pill Isolation** | Retain unprocessable messages for diagnostic redrive | SQS Queue -> DLQ (14-day retention) |
| **Idempotent Dispatch** | Verify uniqueness and publish rich embeds | SQS -> Lambda -> DynamoDB -> Discord |
| **Continuous Delivery** | Deploy container images and infrastructure via OIDC | GitHub Actions -> ECR -> OpenTofu |

![Cloud Feed Pipeline Architecture](architecture.png)

## Tech Stack

| Layer | Tools |
| :--- | :--- |
| **Language** | Python 3.12 (`uv`) |
| **Infrastructure as Code** | OpenTofu 1.9.0 |
| **Compute** | ECS Fargate, Lambda |
| **Messaging & Storage** | SNS, SQS, DynamoDB, S3 |
| **Containerization** | Docker (Multi-stage Alpine, 51.7 MB compressed) |
| **Testing & Quality** | Pytest, Ruff |
| **CI/CD & Security** | GitHub Actions, AWS IAM OIDC |

## Key Architectural Decisions

- **Zero-NAT Gateway Cost Control:** The ECS extractor runs in public subnets with `assign_public_ip = true` and an egress-only security group (`ingress = []`). Drops unsolicited inbound traffic at the hypervisor while avoiding fixed hourly fees from idle NAT Gateways.
- **Decoupled Buffer & Fan-Out:** SNS fan-out to SQS isolates the extractor from Discord rate limits. SQS provides a 180s visibility timeout (6x Lambda timeout) and a 3-retry threshold before quarantining poison pills in a 14-day DLQ.
- **Distributed Idempotency:** Deterministic SHA-256 URL hashing with DynamoDB check-first validation prevents duplicate Discord notifications on SQS retries (`ReportBatchItemFailures` enabled).
- **Hardened Container Profile:** Multi-stage Alpine container drops all Linux capabilities (`drop = ["ALL"]`) and mounts a read-only root filesystem as an unprivileged user (`extractoruser`, UID 10001).

## Documentation

- [Documentation Hub](docs/README.md)
- [Cloud Architecture](docs/architecture.md)
- [Docker Architecture & Benchmarks](docs/docker/README.md)

## Local Development

Test the full event-driven pipeline locally using Podman Compose and LocalStack (emulating S3, SNS, SQS, and DynamoDB offline):

```bash
# Start the stack (boots LocalStack, provisions resources, starts dispatcher)
make compose-up

# Trigger an extraction run in a separate terminal
podman compose run --rm extractor

# Inspect dispatcher logs to verify ingestion and deduplication
podman logs -f cloud-feed-pipeline-dispatcher

# Tear down the stack
make compose-down
```

## Quality Verification & Linting

Run automated unit tests, verification scripts, formatters, and code quality linters:

```bash
make lint           # Run ruff check and format inspection
make test           # Run all unit tests with pytest (20/20 passed)
make md-lint        # Lint markdown documentation files
make tofu-fmt       # Check OpenTofu formatting across all modules
make tofu-validate  # Validate root and sub-module OpenTofu configurations
```
