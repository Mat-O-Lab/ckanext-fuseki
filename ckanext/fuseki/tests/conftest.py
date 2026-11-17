"""Shared fixtures. The tests here need neither a CKAN database nor a running
Fuseki: jobs go to a temporary SQLite file and HTTP calls are mocked."""

import pytest
from ckan.plugins import toolkit


@pytest.fixture
def sqlite_url(tmp_path):
    return "sqlite:///{}".format(tmp_path / "jobs.db")


@pytest.fixture
def job_db(monkeypatch, sqlite_url):
    """Point ckanext.fuseki.db_url at a temporary SQLite database."""
    from ckanext.fuseki import db

    monkeypatch.setitem(toolkit.config, "ckanext.fuseki.db_url", sqlite_url)
    monkeypatch.delenv("FUSEKI_SQLALCHEMY_URL", raising=False)
    db.init()
    yield db
    db.drop_all()
