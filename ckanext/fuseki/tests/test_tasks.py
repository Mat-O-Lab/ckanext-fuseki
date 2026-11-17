import json
import logging
import types

import pytest
import sqlalchemy

from ckanext.fuseki import db, tasks
from ckanext.fuseki.logic import action


def _stub_job(monkeypatch, job_id="job-1"):
    monkeypatch.setattr(tasks, "get_current_job", lambda: types.SimpleNamespace(id=job_id))
    monkeypatch.setattr(tasks.model.meta, "create_local_session", lambda: None)
    callbacks = []

    def fake_callback(result_url, api_key, job_dict):
        # snapshot: the same dict object is mutated by update()
        callbacks.append(json.loads(json.dumps(job_dict, cls=tasks.DatetimeJsonEncoder)))
        return True

    monkeypatch.setattr(tasks, "callback_fuseki_hook", fake_callback)
    return callbacks


def _run_update(job_id="job-1"):
    return tasks.update(
        "ds-name", "ds-id", [], "http://ckan/api/3/action/fuseki_hook", "2026-01-01", reasoner="fullOWL"
    )


def _logged_messages(job_id):
    with db.ENGINE.connect() as conn:
        rows = conn.execute(
            sqlalchemy.select(db.LOGS_TABLE.c.level, db.LOGS_TABLE.c.message).where(
                db.LOGS_TABLE.c.job_id == job_id
            )
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def test_failing_job_is_reported_not_left_pending(monkeypatch, job_db):
    """A job that raises used to stay "pending" and show only its first log
    line. It must now log the failure, report status "error" and re-raise."""
    callbacks = _stub_job(monkeypatch)

    def boom(dataset_id):
        raise RuntimeError("fuseki is down")

    monkeypatch.setattr(tasks.backend, "get_graph", boom)

    with pytest.raises(RuntimeError, match="fuseki is down"):
        _run_update()

    assert callbacks[0]["status"] == "running"
    assert callbacks[-1]["status"] == "error"
    assert callbacks[-1]["error"] == {"message": "RuntimeError: fuseki is down"}
    assert ("ERROR", "Job failed: RuntimeError: fuseki is down") in _logged_messages("job-1")
    logging.getLogger("job-1").handlers.clear()


def test_log_records_are_committed_to_the_db(monkeypatch, job_db):
    """SQLAlchemy 2 does not autocommit; the log handler used to lose rows."""
    handler = tasks.StoringHandler("job-log", {})
    logger = logging.getLogger("job-log")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        logger.info("first")
        logger.warning("second")
    finally:
        logger.removeHandler(handler)
    assert _logged_messages("job-log") == [("INFO", "first"), ("WARNING", "second")]


def test_hook_records_error_in_job_table(monkeypatch, job_db):
    job_db.add_pending_job("job-9", "fuseki", metadata={"pkg_id": "p1"})
    updates = []

    def fake_get_action(name):
        if name == "task_status_show":
            return lambda ctx, data: {"value": json.dumps({"job_id": "job-9"})}
        if name == "task_status_update":
            return lambda ctx, data: updates.append(dict(data))
        raise AssertionError("unexpected action " + name)

    monkeypatch.setattr(action.toolkit, "get_action", fake_get_action)

    action.fuseki_hook(
        {},
        {
            "metadata": {"pkg_id": "p1"},
            "status": "error",
            "job_info": {},
            "error": {"message": "HTTPError: 502"},
        },
    )

    job = job_db.get_job("job-9")
    assert job["status"] == "error"
    assert job["error"]["message"] == "HTTPError: 502"
    assert updates[-1]["state"] == "error"
    assert updates[-1]["error"] == {"message": "HTTPError: 502"}
