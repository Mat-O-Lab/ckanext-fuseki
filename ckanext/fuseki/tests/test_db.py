import json
import logging

import pytest
from ckan.plugins import toolkit

from ckanext.fuseki import db


def test_init_uses_config_option(monkeypatch, sqlite_url):
    monkeypatch.setitem(toolkit.config, "ckanext.fuseki.db_url", sqlite_url)
    monkeypatch.delenv("FUSEKI_SQLALCHEMY_URL", raising=False)
    db.init()
    try:
        assert str(db.ENGINE.url) == sqlite_url
    finally:
        db.drop_all()


def test_explicit_uri_wins_over_config(monkeypatch, tmp_path):
    other = "sqlite:///{}".format(tmp_path / "other.db")
    monkeypatch.setitem(toolkit.config, "ckanext.fuseki.db_url", "sqlite:///ignored.db")
    db.init(other)
    try:
        assert str(db.ENGINE.url) == other
    finally:
        db.drop_all()


def test_legacy_env_var_is_ignored_with_warning(monkeypatch, sqlite_url, tmp_path, caplog):
    legacy = "sqlite:///{}".format(tmp_path / "legacy.db")
    monkeypatch.setitem(toolkit.config, "ckanext.fuseki.db_url", sqlite_url)
    monkeypatch.setenv("FUSEKI_SQLALCHEMY_URL", legacy)
    with caplog.at_level(logging.WARNING, logger="ckanext.fuseki.db"):
        db.init()
    try:
        assert str(db.ENGINE.url) == sqlite_url
        assert "FUSEKI_SQLALCHEMY_URL is no longer used" in caplog.text
    finally:
        db.drop_all()


def test_job_lifecycle(job_db):
    db.add_pending_job("job-1", "fuseki", data={"a": 1}, metadata={"pkg_id": "p1"})
    assert db.get_job("job-1")["status"] == "pending"

    db.mark_job_as_errored("job-1", {"message": "boom"})
    job = db.get_job("job-1")
    assert job["status"] == "error"
    assert "boom" in json.dumps(job["error"])


def test_job_completed(job_db):
    db.add_pending_job("job-2", "fuseki")
    db.mark_job_as_completed("job-2")
    assert db.get_job("job-2")["status"] == "complete"


def test_invalid_error_object_rejected(job_db):
    db.add_pending_job("job-3", "fuseki")
    with pytest.raises(db.InvalidErrorObjectError):
        db.mark_job_as_errored("job-3", {"no_message": 1})
