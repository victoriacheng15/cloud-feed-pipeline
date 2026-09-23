import json
import logging
import os
import sys
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


def load_feeds(file_path: str = "feeds.json") -> list[dict]:
    if CONFIG_BUCKET:
        logger.info("Loading feeds configuration from cloud storage")
        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=CONFIG_BUCKET, Key="feeds.json")
        return json.load(response["Body"])

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

    except Exception as err:
        logger.critical("Fatal extractor error: %s", str(err), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
