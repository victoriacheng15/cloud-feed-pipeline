# /// script
# dependencies = [
#     "diagrams>=0.23.4",
# ]
# ///
"""Generate architecture diagram using Python Diagrams.

How to run:
    uv run scripts/generate_diagram.py
    # or
    uv run --with diagrams python scripts/generate_diagram.py
"""

from diagrams import Diagram, Edge
from diagrams.aws.compute import ECS, Lambda
from diagrams.aws.database import Dynamodb
from diagrams.aws.integration import SNS, SQS, Eventbridge
from diagrams.aws.storage import S3
from diagrams.saas.chat import Discord

graph_attr = {
    "fontsize": "13",
    "bgcolor": "#FFFFFF",
    "pad": "0.5",
    "splines": "ortho",
}

node_attr = {
    "fontsize": "10",
    "fontname": "Sans-Serif",
}

edge_attr = {
    "color": "#4B5563",
    "fontsize": "9",
    "fontname": "Sans-Serif",
}

with Diagram(
    "Cloud Pipeline Architecture",
    show=False,
    filename="architecture",
    outformat="png",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    eb = Eventbridge("EventBridge\n(Cron: Tue, Thu 02:16 UTC)")
    ecs = ECS("ECS Extractor\n(Fargate)")
    s3 = S3("S3 Config")
    sns = SNS("SNS Topic\n(Feed Events)")
    sqs = SQS("SQS Queue")
    dlq = SQS("SQS DLQ\n(14d / 3 retries)")
    fn = Lambda("Lambda Dispatch\n(Python 3.12, 30s)")
    ddb = Dynamodb("DynamoDB\n(Check / Commit)")
    discord = Discord("Discord\n(Webhook API)")

    # Flow
    eb >> Edge(label="ecs:RunTask") >> ecs
    s3 >> Edge(label="feeds.json", style="dashed") >> ecs
    ecs >> Edge(label="Publishes JSON events") >> sns
    sns >> Edge(label="Fanout subscription") >> sqs
    sqs >> Edge(label="Batches 10 items\n(ReportBatchItemFailures)") >> fn
    sqs >> Edge(label="3 retries", style="dotted", color="#EF4444") >> dlq
    fn >> Edge(label="Check / Commit") >> ddb
    fn >> Edge(label="Deliver embed payload") >> discord
