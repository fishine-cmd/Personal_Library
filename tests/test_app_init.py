"""create_app should surface db.create_all() failures via the logger,
not silently swallow them."""

import logging

import pytest

from app import create_app
from app.extensions import db


def test_create_app_logs_when_db_create_all_fails(monkeypatch, caplog):
    def boom():
        raise RuntimeError("db is unreachable")

    monkeypatch.setattr(db, "create_all", boom)

    with caplog.at_level(logging.ERROR):
        app = create_app("test")

    assert app is not None, "app should still be usable for error pages"
    assert any(
        "db is unreachable" in record.getMessage()
        or (record.exc_info and "db is unreachable" in str(record.exc_info[1]))
        for record in caplog.records
    ), "db.create_all() failure must be logged, not silently swallowed"
