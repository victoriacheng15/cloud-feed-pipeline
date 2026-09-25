import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import feedparser
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("extractor")

CONFIG_BUCKET = os.environ.get("CONFIG_BUCKET")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")


def wait_for_topic(
    sns_client, topic_arn: str, max_retries: int = 30, delay: int = 2
) -> None:
    logger.info("Waiting for SNS topic [%s] to become available...", topic_arn)
    for attempt in range(1, max_retries + 1):
        try:
            sns_client.get_topic_attributes(TopicArn=topic_arn)
            logger.info("Connected to SNS topic: %s", topic_arn)
            return
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "SNS topic [%s] not ready yet (attempt %d/%d): %s",
                topic_arn,
                attempt,
                max_retries,
                str(err),
            )
            time.sleep(delay)
    raise RuntimeError(
        f"SNS topic [{topic_arn}] was not found after {max_retries} attempts"
    )


def publish_article(sns_client, article: dict, topic_arn: str) -> None:
    sns_client.publish(
        TopicArn=topic_arn,
        Message=json.dumps(article),
    )
    logger.info("Published article to SNS: %s", article.get("url"))


def load_feeds(
    file_path: str = "feeds.json", max_retries: int = 15, delay: int = 2
) -> list[dict]:
    if CONFIG_BUCKET:
        logger.info("Loading feeds configuration from cloud storage: %s", CONFIG_BUCKET)
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
        s3 = (
            boto3.client("s3", endpoint_url=endpoint_url)
            if endpoint_url
            else boto3.client("s3")
        )
        for attempt in range(1, max_retries + 1):
            try:
                response = s3.get_object(Bucket=CONFIG_BUCKET, Key="feeds.json")
                return json.load(response["Body"])
            except Exception as err:  # noqa: BLE001
                logger.warning(
                    "Config bucket not ready yet (attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    str(err),
                )
                time.sleep(delay)
        raise RuntimeError(
            f"Failed to load feeds.json from {CONFIG_BUCKET} after {max_retries} attempts"
        )

    logger.info("Loading feeds configuration from local file")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def process_feed(feed: dict) -> list[dict]:
    name = feed.get("name", "Unknown Feed")
    url = feed.get("url")

    if not url:
        logger.warning("Skipping entry missing 'url': %s", feed)
        return []

    logger.info("Fetching feed [%s]", name)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CloudFeedPipeline/1.0; +https://github.com/victoriacheng15/cloud-feed-pipeline)"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            logger.warning(
                "Feed [%s] error parsing content: %s", name, parsed.bozo_exception
            )
            return []

        articles = []
        for entry in parsed.entries:
            title = getattr(entry, "title", "Untitled")
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "")[:200]

            if title and link:
                articles.append(
                    {
                        "feed": name,
                        "title": title,
                        "url": link,
                        "summary": summary,
                    }
                )

        logger.info("Discovered %d articles in [%s]", len(articles), name)
        return articles
    except requests.RequestException as err:
        logger.error("Failed fetching [%s]: %s", name, str(err))
        return []


def main():
    try:
        feeds = load_feeds()
        active = [f for f in feeds if f.get("enabled", True)]
        logger.info("Loaded %d active feeds to process", len(active))

        all_articles = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_feed = {executor.submit(process_feed, f): f for f in active}
            for future in as_completed(future_to_feed):
                articles = future.result()
                all_articles.extend(articles)

        logger.info(
            "Extraction complete. Total articles extracted across all feeds: %d",
            len(all_articles),
        )

        if SNS_TOPIC_ARN:
            endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
            sns = (
                boto3.client("sns", endpoint_url=endpoint_url)
                if endpoint_url
                else boto3.client("sns")
            )
            wait_for_topic(sns, SNS_TOPIC_ARN)

            logger.info(
                "Publishing %d articles to SNS topic: %s",
                len(all_articles),
                SNS_TOPIC_ARN,
            )
            published_count = 0
            for article in all_articles:
                try:
                    publish_article(sns, article, SNS_TOPIC_ARN)
                    published_count += 1
                except Exception as err:  # noqa: BLE001
                    logger.error(
                        "Failed publishing article [%s]: %s",
                        article.get("url"),
                        str(err),
                    )
            logger.info("Successfully published %d articles to SNS", published_count)

    except Exception as err:
        logger.critical("Fatal extractor error: %s", str(err), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
