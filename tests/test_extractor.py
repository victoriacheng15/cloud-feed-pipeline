import io
import json
from unittest.mock import MagicMock

import pytest
import requests

from src.extractor import load_feeds, process_feed

SAMPLE_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Cloud Architecture Blog</title>
    <link>https://example.com/blog</link>
    <description>Engineering updates</description>
    <item>
      <title>Building Serverless Pipelines</title>
      <link>https://example.com/blog/serverless-pipelines</link>
      <description>A guide to event-driven architectures with AWS and Python.</description>
    </item>
    <item>
      <title>Optimizing Container Workloads</title>
      <link>https://example.com/blog/optimizing-containers</link>
      <description>Best practices for multi-stage Docker builds on ECS.</description>
    </item>
  </channel>
</rss>
"""


@pytest.mark.parametrize(
    "file_content, filename, want_err, expected_count",
    [
        pytest.param(
            json.dumps(
                [
                    {
                        "id": "feed-1",
                        "name": "Feed One",
                        "url": "https://example.com/1",
                        "enabled": True,
                    }
                ]
            ),
            "feeds.json",
            False,
            1,
            id="happy_path_valid_json",
        ),
        pytest.param(
            None,
            "nonexistent_file.json",
            True,
            0,
            id="file_not_found_raises",
        ),
    ],
)
def test_load_feeds_local(tmp_path, file_content, filename, want_err, expected_count):
    target_path = tmp_path / filename
    if file_content is not None:
        target_path.write_text(file_content, encoding="utf-8")

    if want_err:
        with pytest.raises(FileNotFoundError):
            load_feeds(str(target_path))
    else:
        result = load_feeds(str(target_path))
        assert len(result) == expected_count
        assert result[0]["id"] == "feed-1"


@pytest.mark.parametrize(
    "bucket_env, s3_feeds, want_s3_call",
    [
        pytest.param(
            "test-config-bucket",
            [
                {
                    "id": "s3-feed",
                    "name": "S3 Cloud Feed",
                    "url": "https://example.com/s3",
                    "enabled": True,
                }
            ],
            True,
            id="s3_bucket_configured",
        ),
    ],
)
def test_load_feeds_s3(monkeypatch, bucket_env, s3_feeds, want_s3_call):
    monkeypatch.setattr("src.extractor.CONFIG_BUCKET", bucket_env)
    body_stream = io.BytesIO(json.dumps(s3_feeds).encode("utf-8"))

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": body_stream}
    monkeypatch.setattr("boto3.client", lambda service: mock_s3)

    result = load_feeds()
    assert len(result) == 1
    assert result[0]["id"] == "s3-feed"
    mock_s3.get_object.assert_called_once_with(Bucket=bucket_env, Key="feeds.json")


@pytest.mark.parametrize(
    "feed_input, mock_response_body, mock_exception, expected_article_count",
    [
        pytest.param(
            {
                "id": "valid-feed",
                "name": "Cloud Blog",
                "url": "https://example.com/feed",
            },
            SAMPLE_RSS_XML,
            None,
            2,
            id="happy_path_two_entries",
        ),
        pytest.param(
            {"id": "missing-url", "name": "No URL Feed"},
            None,
            None,
            0,
            id="missing_url_returns_empty",
        ),
        pytest.param(
            {},
            None,
            None,
            0,
            id="empty_feed_config_returns_empty",
        ),
        pytest.param(
            {
                "id": "timeout-feed",
                "name": "Timeout Blog",
                "url": "https://timeout.example.com",
            },
            None,
            requests.RequestException("Connection timeout"),
            0,
            id="network_exception_handled_gracefully",
        ),
        pytest.param(
            {
                "id": "bad-xml-feed",
                "name": "Bad XML Blog",
                "url": "https://bad.example.com",
            },
            b"<html><body>502 Bad Gateway</body></html>",
            None,
            0,
            id="bozo_invalid_xml_handled_gracefully",
        ),
    ],
)
def test_process_feed(
    monkeypatch, feed_input, mock_response_body, mock_exception, expected_article_count
):
    if mock_exception is not None:
        monkeypatch.setattr(requests, "get", MagicMock(side_effect=mock_exception))
    elif mock_response_body is not None:
        mock_resp = MagicMock()
        mock_resp.content = mock_response_body
        mock_resp.raise_for_status = MagicMock()
        monkeypatch.setattr(requests, "get", MagicMock(return_value=mock_resp))

    articles = process_feed(feed_input)
    assert len(articles) == expected_article_count

    if expected_article_count > 0:
        assert articles[0]["title"] == "Building Serverless Pipelines"
        assert articles[0]["url"] == "https://example.com/blog/serverless-pipelines"
        assert articles[0]["feed"] == "Cloud Blog"
