"""Ingest validates and normalizes fixtures."""

from __future__ import annotations

import json

import pytest

from router.config import SAMPLE_DATA_DIR
from router.ingest import ingest_files


def test_ingests_sample_fixtures():
    msgs = ingest_files(
        [SAMPLE_DATA_DIR / "emails.json", SAMPLE_DATA_DIR / "slack.json"]
    )
    assert len(msgs) == 6
    # Sorted by received time.
    times = [m.received_at for m in msgs]
    assert times == sorted(times)


def test_rejects_empty_body(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            [
                {
                    "id": "x-1",
                    "channel": "email",
                    "sender_name": "Alex",
                    "sender_email": "alex@example.com",
                    "subject": "hi",
                    "body": "   ",
                    "received_at": "2026-06-18T09:00:00+00:00",
                }
            ]
        )
    )
    with pytest.raises(ValueError):
        ingest_files([bad])


def test_rejects_unknown_channel(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            [
                {
                    "id": "x-1",
                    "channel": "carrier_pigeon",
                    "sender_name": "Alex",
                    "sender_email": "alex@example.com",
                    "subject": "hi",
                    "body": "hello",
                    "received_at": "2026-06-18T09:00:00+00:00",
                }
            ]
        )
    )
    with pytest.raises(ValueError):
        ingest_files([bad])
