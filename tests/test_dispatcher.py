import hashlib
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from src.dispatcher import (
    dispatch_to_discord,
    get_table,
    lambda_handler,
    process_record,
)


@pytest.mark.parametrize(
    "article, url, webhook_env, mock_status, expect_error",
    [
        pytest.param(
            {
                "title": "AWS ECS Guide",
                "summary": "Running Fargate",
                "source": "AWS Blog",
            },
            "https://aws.amazon.com/blogs/compute/ecs-guide",
            "https://discord.com/api/webhooks/test",
            204,
            None,
            id="successful_dispatch",
        ),
        pytest.param(
            {"title": "Fail Post"},
            "https://example.com/fail",
            "https://discord.com/api/webhooks/test",
            500,
            urllib.error.HTTPError,
            id="discord_http_error",
        ),
        pytest.param(
            {"title": "No Webhook Env"},
            "https://example.com/no-url",
            None,
            None,
            ValueError,
            id="missing_webhook_url",
        ),
    ],
)
def test_dispatch_to_discord(
    monkeypatch, article, url, webhook_env, mock_status, expect_error
):
    if webhook_env:
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", webhook_env)
    else:
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    if expect_error == ValueError:
        with pytest.raises(ValueError, match="DISCORD_WEBHOOK_URL"):
            dispatch_to_discord(article, url)
        return

    if expect_error == urllib.error.HTTPError:
        err = urllib.error.HTTPError(
            url=webhook_env,
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None,
        )
        with (
            patch("urllib.request.urlopen", side_effect=err),
            pytest.raises(urllib.error.HTTPError),
        ):
            dispatch_to_discord(article, url)
        return

    mock_resp = MagicMock()
    mock_resp.status = mock_status
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        dispatch_to_discord(article, url)
        assert mock_urlopen.call_count == 1
        req_arg = mock_urlopen.call_args[0][0]
        payload = json.loads(req_arg.data.decode("utf-8"))
        assert payload["embeds"][0]["url"] == url
        assert payload["embeds"][0]["title"] == article["title"]


@pytest.mark.parametrize(
    "raw_record, existing_item, should_dispatch, should_save",
    [
        pytest.param(
            {
                "messageId": "msg-new-sns",
                "body": json.dumps(
                    {
                        "Message": json.dumps(
                            {
                                "title": "New Cloud Post",
                                "url": "https://aws.amazon.com/post-1",
                                "source": "AWS",
                            }
                        )
                    }
                ),
            },
            None,
            True,
            True,
            id="new_article_sns_envelope",
        ),
        pytest.param(
            {
                "messageId": "msg-new-direct",
                "body": json.dumps(
                    {
                        "title": "Direct Body Article",
                        "url": "https://aws.amazon.com/post-direct",
                        "source": "Direct",
                    }
                ),
            },
            None,
            True,
            True,
            id="new_article_direct_body",
        ),
        pytest.param(
            {
                "messageId": "msg-duplicate",
                "body": json.dumps(
                    {
                        "title": "Duplicate Post",
                        "url": "https://aws.amazon.com/duplicate",
                    }
                ),
            },
            {"article_hash": "existing-hash"},
            False,
            False,
            id="duplicate_article_dropped",
        ),
        pytest.param(
            {
                "messageId": "msg-no-url",
                "body": json.dumps({"title": "No URL Post"}),
            },
            None,
            False,
            False,
            id="missing_url_skipped",
        ),
    ],
)
def test_process_record_deduplication(
    raw_record, existing_item, should_dispatch, should_save
):
    mock_table = MagicMock()
    mock_table.get_item.return_value = {"Item": existing_item} if existing_item else {}

    with patch("src.dispatcher.dispatch_to_discord") as mock_dispatch:
        process_record(raw_record, table=mock_table)

        if should_dispatch:
            assert mock_dispatch.call_count == 1
        else:
            mock_dispatch.assert_not_called()

        if should_save:
            assert mock_table.put_item.call_count == 1
            put_kwargs = mock_table.put_item.call_args[1]
            saved_item = put_kwargs["Item"]
            expected_hash = hashlib.sha256(
                saved_item["url"].encode("utf-8")
            ).hexdigest()
            assert saved_item["article_hash"] == expected_hash
            assert "dispatched_at" in saved_item
        else:
            mock_table.put_item.assert_not_called()


def test_process_record_dispatch_failure_does_not_save_to_dynamo():
    record = {
        "messageId": "msg-fail",
        "body": json.dumps(
            {
                "title": "Failing Article",
                "url": "https://example.com/fail-article",
            }
        ),
    }
    mock_table = MagicMock()
    mock_table.get_item.return_value = {}

    with (
        patch(
            "src.dispatcher.dispatch_to_discord",
            side_effect=RuntimeError("Discord API Down"),
        ),
        pytest.raises(RuntimeError, match="Discord API Down"),
    ):
        process_record(record, table=mock_table)

    mock_table.put_item.assert_not_called()


@pytest.mark.parametrize(
    "records, failing_ids, expected_failures",
    [
        pytest.param(
            [
                {"messageId": "rec-1", "body": "{}"},
                {"messageId": "rec-2", "body": "{}"},
            ],
            [],
            [],
            id="all_records_succeed",
        ),
        pytest.param(
            [
                {"messageId": "rec-1", "body": "{}"},
                {"messageId": "rec-2", "body": "{}"},
                {"messageId": "rec-3", "body": "{}"},
            ],
            ["rec-2"],
            [{"itemIdentifier": "rec-2"}],
            id="partial_batch_failure",
        ),
        pytest.param(
            [],
            [],
            [],
            id="empty_batch",
        ),
    ],
)
def test_lambda_handler(records, failing_ids, expected_failures):
    def fake_process_record(record):
        if record.get("messageId") in failing_ids:
            raise RuntimeError("Processing failed")

    with patch("src.dispatcher.process_record", side_effect=fake_process_record):
        result = lambda_handler({"Records": records})
        assert result == {"batchItemFailures": expected_failures}


def test_get_table_configuration(monkeypatch):
    monkeypatch.delenv("DYNAMODB_TABLE", raising=False)
    monkeypatch.setattr("src.dispatcher._table", None)

    with pytest.raises(ValueError, match="DYNAMODB_TABLE"):
        get_table()

    monkeypatch.setenv("DYNAMODB_TABLE", "test-table")
    mock_boto = MagicMock()
    monkeypatch.setattr("boto3.resource", lambda service: mock_boto)

    tbl = get_table()
    mock_boto.Table.assert_called_once_with("test-table")
    assert tbl == mock_boto.Table.return_value
