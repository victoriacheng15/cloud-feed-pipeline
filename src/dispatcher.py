import hashlib
import json
import logging
import os
import time
import urllib.request

import boto3

logger = logging.getLogger("dispatcher")
logger.setLevel(logging.INFO)

_table = None


def get_table():
    global _table
    if _table is None:
        table_name = os.environ.get("DYNAMODB_TABLE")
        if not table_name:
            raise ValueError("DYNAMODB_TABLE environment variable is not set")
        dynamodb = boto3.resource("dynamodb")
        _table = dynamodb.Table(table_name)
    return _table


def dispatch_to_discord(
    article: dict, url: str, webhook_url: str | None = None
) -> None:
    target_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
    if not target_url:
        raise ValueError("DISCORD_WEBHOOK_URL environment variable is not set")

    embed = {
        "embeds": [
            {
                "title": article.get("title", "New Article Detected"),
                "url": url,
                "description": article.get("summary", ""),
                "color": 3447003,
                "fields": [
                    {
                        "name": "Source",
                        "value": article.get("source", "Web"),
                        "inline": True,
                    }
                ],
                "footer": {"text": "Cloud Pipeline Bot | Idempotent Dispatch"},
            }
        ]
    }

    req = urllib.request.Request(
        target_url,
        data=json.dumps(embed).encode("utf-8"),
        headers={
            "User-Agent": "AWS-Lambda-Pipeline/1.0",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        logger.info("Discord returned status code: %d", response.status)


def process_record(record: dict, table=None) -> None:
    body = record.get("body", "{}")
    parsed_body = json.loads(body) if isinstance(body, str) else body

    if isinstance(parsed_body, dict) and "Message" in parsed_body:
        message_raw = parsed_body["Message"]
        article = (
            json.loads(message_raw) if isinstance(message_raw, str) else message_raw
        )
    else:
        article = parsed_body

    url = article.get("url")
    if not url:
        logger.warning("Skipping payload missing 'url' field")
        return

    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
    active_table = table if table is not None else get_table()

    # Step 1: Idempotency Check in DynamoDB
    response = active_table.get_item(Key={"article_hash": url_hash})
    if "Item" in response:
        logger.info("Article already dispatched previously. Dropping: %s", url)
        return

    # Step 2: Format & Send Discord Webhook Payload
    dispatch_to_discord(article, url)

    # Step 3: Record Dispatched Hash on Success
    active_table.put_item(
        Item={
            "article_hash": url_hash,
            "url": url,
            "title": article.get("title", ""),
            "dispatched_at": int(time.time()),
        }
    )
    logger.info("Dispatched and recorded new unique article: %s", url)


def lambda_handler(event: dict, context=None) -> dict:
    records = event.get("Records", [])
    logger.info("Processing event batch containing %d records", len(records))
    batch_item_failures = []

    for record in records:
        try:
            process_record(record)
        except Exception:
            message_id = record.get("messageId", "unknown")
            logger.exception(
                "Failed processing record %s",
                message_id,
            )
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
