# Cloud Feed Pipeline Architecture

Technical architecture specification for the Cloud Feed Pipeline, detailing system topology, component interactions, failure resilience, and network design.

---

## 1. System Blueprint

The pipeline follows an asynchronous, event-driven decoupled architecture:

```
                  ┌───────────────────────────────┐
                  │          EventBridge          │
                  │   cron(16 2 ? * TUE,THU *)    │
                  └──────────────┬────────────────┘
                                 │
                                 │ ecs:RunTask
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ECS Fargate Task                          │
│             (ca-central-1 Public Subnet, Egress-Only)           │
│                                                                 │
│   ┌───────────────┐     ┌────────────────┐     ┌────────────┐   │
│   │ S3 feeds.json │ ──> │ RSS Extractor  │ ──> │ SNS Client │   │
│   │   Registry    │     │  (Concurrent)  │     │ (Publish)  │   │
│   └───────────────┘     └────────────────┘     └─────┬──────┘   │
└──────────────────────────────────────────────────────┼──────────┘
                                                       │
                                                       │ Publish article JSON
                                                       ▼
                                          ┌────────────────────────┐
                                          │       SNS Topic        │
                                          │     (Feed Events)      │
                                          └────────────┬───────────┘
                                                       │
                                                       │ Fan-Out Subscription
                                                       ▼
                                          ┌────────────────────────┐
                                          │       SQS Queue        │
                                          │    (Pipeline Queue)    │
                                          └────┬──────────────┬────┘
                                               │              │
                    Batches of up to 10 items  │              │ 3 failed retries
                 with ReportBatchItemFailures  │              ▼
                                               │     ┌─────────────────┐
                                               │     │  Dead-Letter Q  │
                                               │     │ (14-d retention)│
                                               │     └─────────────────┘
                                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Lambda Dispatcher                         │
│                       (Python 3.12, 30s timeout)                │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ For each SQS message:                                   │   │
│   │                                                         │   │
│   │ 1. Compute SHA-256 hash of article URL                  │   │
│   │ 2. DynamoDB GetItem(article_hash)                       │   │
│   │    ├── Exists: Discard (duplicate, return success)      │   │
│   │    └── New: Format Discord rich embed                   │   │
│   │ 3. HTTP POST to Discord Webhook                         │   │
│   │    ├── Success (2xx/204): DynamoDB PutItem(article_hash)│   │
│   │    └── Failure (4xx/5xx): ReportBatchItemFailures       │   │
│   └─────────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────┬───────────────┘
                        │                         │
     Check / Commit     ▼                         ▼ Deliver Embed
  ┌───────────────────────────┐         ┌─────────────────────────┐
  │      DynamoDB Table       │         │   Discord Webhook API   │
  │   (Deduplication Store)   │         │   (Rich Embed Post)     │
  └───────────────────────────┘         └─────────────────────────┘
```

---

## 2. Ingestion & Extractor Subsystem

### Ephemeral Execution Model
The extractor parses multiple RSS feeds concurrently. Instead of maintaining a persistent server or using Lambda (which risks execution timeouts on slow upstream feed hosts), the service runs as an on-demand ECS Fargate container:
- **Scheduler:** EventBridge invokes the task on Tuesdays and Thursdays at 02:16 UTC.
- **Feed Registry:** The task reads `feeds.json` from the S3 configuration bucket using the task IAM role.
- **Concurrent Ingestion:** Feeds parse concurrently with per-host timeout boundaries to isolate slow or unresponsive servers.
- **Container Footprint:** Built on Alpine Linux (51.7 MB compressed) with read-only root filesystems and dropped Linux kernel capabilities.

### Zero-NAT Gateway Egress Topology
Running ECS containers in private subnets typically requires an AWS NAT Gateway, which incurs fixed hourly fees even when idle. To avoid this cost while securing the network perimeter:

```
                      INTERNET
                         │
                         ▼
        ┌──────────────────────────────────┐
        │       AWS VPC Public Subnet      │
        │                                  │
        │   ┌──────────────────────────┐   │
        │   │    ECS Fargate ENI       │   │
        │   │  (Ephemeral Public IP)   │   │
        │   │                          │   │
        │   │  Security Group Rules:   │   │
        │   │  - Ingress: NONE []      │   │ <── Drops all unsolicited
        │   │  - Egress: 80, 443, 53   │   │     inbound packets at
        │   └─────────────┬────────────┘   │     hypervisor layer
        │                 │                │
        └─────────────────┼────────────────┘
                          │
                          │ Outbound HTTPS (443) / DNS (53) only
                          ▼
            [RSS Feeds / ECR / AWS APIs]
```

1. **Ephemeral Public IP:** The task launches with `assign_public_ip = true`.
2. **Egress-Only Security Group:** The security group defines zero inbound rules (`ingress = []`). The AWS hypervisor drops 100% of unsolicited inbound packets before reaching the container.
3. **Stateful Connection Tracking:** AWS security groups track outbound requests statefully, allowing inbound response packets for outbound HTTPS (443) and DNS (53) traffic.

---

## 3. Messaging, Buffering & Resilience

### Asynchronous Fan-Out
The extractor publishes individual article events to an SNS topic. This provides architectural decoupling:
- The extractor completes immediately after publishing without waiting for downstream processing.
- Additional subscribers (such as archive storage or analytics) can attach to the topic without changes to the extractor.

### Backpressure & Queue Buffering
The SNS topic delivers messages to an SQS queue:
- **Dampening Spikes:** Feeds published simultaneously are buffered in SQS, preventing downstream Lambda invocations from exhausting concurrent execution limits or triggering Discord rate limits.
- **Visibility Timeout:** Configured to 180 seconds, exactly 6x the Lambda 30-second timeout. This ensures in-flight batches have sufficient margin to complete without premature redelivery.

### Poison-Pill Quarantine & DLQ Flow
```
[Incoming SQS Message] ──> [Lambda Execution Attempt]
                                    │
                       ┌────────────┴────────────┐
                       ▼                         ▼
                  [Success]                  [Failure]
                      │                          │
                 (Delete msg)            (Increment ReceiveCount)
                                                 │
                                     ReceiveCount >= 3 ?
                                    ┌────────────┴────────────┐
                                    ▼                         ▼
                                   [No]                     [Yes]
                                    │                         │
                             (Return to SQS)        (Move to DLQ, 14-day retention)
```

1. SQS tracks delivery attempts per message (`ApproximateReceiveCount`).
2. If processing fails 3 consecutive times, SQS moves the message to the Dead-Letter Queue.
3. The DLQ retains poisoned messages for 14 days, allowing manual inspection and replay without blocking healthy traffic.

---

## 4. Deduplication & Idempotent Dispatch

### Check-First Deduplication Pattern
SQS provides at-least-once delivery guarantees, which can cause duplicate executions during retries or network partitions. The Lambda dispatcher guarantees exactly-once delivery semantics using a check-first pattern:

```
[SQS Message Received]
          │
          ▼
[Compute SHA-256 Hash of Canonical URL]
          │
          ▼
[DynamoDB GetItem(article_hash)]
          │
     Hash Exists?
    ┌─────┴─────┐
    ▼           ▼
  [Yes]        [No]
    │           │
(Discard)       ▼
(Success)  [Format Discord Rich Embed]
                │
                ▼
           [HTTP POST to Discord Webhook]
                │
           Status 2xx/204?
          ┌─────┴─────┐
          ▼           ▼
        [Yes]        [No]
          │           │
[DynamoDB PutItem] [ReportBatchItemFailures]
(Record Hash)      (Leave on SQS for retry)
```

1. **Deterministic Keying:** Each article URL is hashed with SHA-256 into a 64-character hexadecimal digest.
2. **Pre-Dispatch Evaluation:** Lambda reads DynamoDB (`GetItem`) before contacting Discord. If the hash exists, the article is logged as a duplicate and dismissed.
3. **Atomic Commit Post-Delivery:** The hash is committed to DynamoDB (`PutItem`) only after the Discord webhook returns an HTTP 2xx or 204 response.
4. **Failure Safety:** If Discord returns a 429 (rate limit) or 5xx (server error), the hash is not written, ensuring SQS will safely redeliver the message on the next attempt.

### Partial Batch Failure Handling
Lambda processes messages in batches of up to 10:
- The event source mapping has `ReportBatchItemFailures` enabled.
- If message 3 in a 10-message batch fails, Lambda reports only message 3's identifier in `batchItemFailures`.
- Messages 1, 2, and 4 through 10 are deleted from the queue, preventing duplicate notifications.

---

## 5. Infrastructure as Code & State Management

Infrastructure is managed with OpenTofu in modular components:

| Module | Core Resources | Responsibility |
| :--- | :--- | :--- |
| `infra/storage/` | DynamoDB Table, S3 Config Bucket | State storage and feed registry |
| `infra/messaging/` | SNS Topic, SQS Queue, SQS DLQ | Decoupled buffering and routing |
| `infra/extractor/` | ECS Cluster, Task Definition, Security Group, EventBridge | Ingestion compute and scheduling |
| `infra/dispatcher/` | Lambda Function, SQS Event Mapping, IAM Execution Role | Processing and delivery |

- **Remote Backend:** Root `infra/main.tf` stores state remotely in an S3 backend in `ca-central-1`.
- **CI/CD Integration:** Merges to `main` authenticate via AWS OIDC federation, publish container images to Amazon ECR, and execute `tofu apply -auto-approve` without long-lived credentials.
