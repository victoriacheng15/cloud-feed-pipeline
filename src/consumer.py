import argparse
import logging
import os
import sys
import time
import urllib.parse

import boto3

from src.dispatcher import lambda_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sqs-consumer")


def get_queue_url(
    sqs_client, queue_name: str, max_retries: int = 30, delay: int = 2
) -> str:
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    logger.info("Waiting for SQS queue [%s] to become available...", queue_name)
    for attempt in range(1, max_retries + 1):
        try:
            response = sqs_client.get_queue_url(QueueName=queue_name)
            queue_url = response["QueueUrl"]
            if endpoint_url:
                parsed_ep = urllib.parse.urlparse(endpoint_url)
                parsed_q = urllib.parse.urlparse(queue_url)
                queue_url = urllib.parse.urlunparse(
                    (parsed_ep.scheme, parsed_ep.netloc, parsed_q.path, "", "", "")
                )
            logger.info("Connected to SQS queue: %s", queue_url)
            return queue_url
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "Queue [%s] not ready yet (attempt %d/%d): %s",
                queue_name,
                attempt,
                max_retries,
                str(err),
            )
            time.sleep(delay)
    raise RuntimeError(
        f"Queue [{queue_name}] was not found after {max_retries} attempts"
    )


def poll_and_dispatch(
    queue_name: str = "cloud-feed-pipeline-queue",
    max_messages: int = 10,
    wait_time_seconds: int = 5,
    once: bool = False,
) -> int:
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    region_name = os.environ.get("AWS_DEFAULT_REGION", "ca-central-1")

    sqs = boto3.client("sqs", endpoint_url=endpoint_url, region_name=region_name)
    queue_url = get_queue_url(sqs, queue_name)
    logger.info("Polling SQS queue: %s (endpoint=%s)", queue_url, endpoint_url)

    total_processed = 0

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=wait_time_seconds,
            )

            messages = response.get("Messages", [])
            if not messages:
                if once:
                    logger.info("No messages in queue. Exiting (--once).")
                    break
                logger.debug("No messages received, waiting...")
                time.sleep(2)
                continue

            logger.info("Received %d messages from queue", len(messages))

            records = [
                {
                    "messageId": msg["MessageId"],
                    "receiptHandle": msg["ReceiptHandle"],
                    "body": msg["Body"],
                    "attributes": msg.get("Attributes", {}),
                    "messageAttributes": msg.get("MessageAttributes", {}),
                    "md5OfBody": msg.get("MD5OfBody", ""),
                    "eventSource": "aws:sqs",
                    "eventSourceARN": f"arn:aws:sqs:{region_name}:000000000000:{queue_name}",
                    "awsRegion": region_name,
                }
                for msg in messages
            ]

            # Invoke standard Lambda handler
            lambda_handler({"Records": records})

            # Delete processed messages
            for msg in messages:
                sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )

            total_processed += len(messages)
            logger.info("Successfully processed and deleted %d messages", len(messages))

            if once:
                break

        except KeyboardInterrupt:
            logger.info("Consumer stopped by user.")
            break
        except Exception:
            logger.exception("Consumer encountered error")
            if once:
                raise
            time.sleep(5)

    return total_processed


def main():
    parser = argparse.ArgumentParser(description="Local SQS Dispatcher Consumer")
    parser.add_argument(
        "--queue",
        default=os.environ.get("SQS_QUEUE_NAME", "cloud-feed-pipeline-queue"),
        help="SQS Queue Name to poll",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Poll once and exit instead of continuous loop",
    )
    args = parser.parse_args()

    poll_and_dispatch(queue_name=args.queue, once=args.once)


if __name__ == "__main__":
    main()
