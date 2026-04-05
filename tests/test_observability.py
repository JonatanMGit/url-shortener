import json
import logging

from flask import Flask

from app.observability import configure_logging


def test_metrics_endpoint_returns_cpu_and_memory(client):
    response = client.get("/metrics")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["kind"] == "metrics"

    sample = payload["sample"]
    assert isinstance(sample["cpu_percent"], (int, float))

    memory = sample["memory"]
    assert memory["total_mb"] > 0
    assert memory["available_mb"] >= 0
    assert memory["used_mb"] >= 0
    assert isinstance(memory["percent"], (int, float))

    process = sample["process"]
    assert process["pid"] > 0
    assert process["rss_mb"] >= 0
    assert process["threads"] >= 1
    assert process["uptime_seconds"] >= 0


def test_request_logging_emits_http_record(app, caplog):
    client = app.test_client()

    with caplog.at_level(logging.INFO):
        response = client.get("/health")

    assert response.status_code == 200

    matching = [record for record in caplog.records if record.msg == "request_complete"]
    assert matching

    record = matching[-1]
    assert record.levelname == "INFO"
    assert getattr(record, "component", None) == "http"
    assert getattr(record, "method", None) == "GET"
    assert getattr(record, "path", None) == "/health"
    assert getattr(record, "status_code", None) == 200


def test_request_logging_emits_warning_for_client_errors(app, caplog):
    client = app.test_client()

    with caplog.at_level(logging.INFO):
        response = client.post("/users", json={"username": "missing_email"})

    assert response.status_code == 400

    matching = [record for record in caplog.records if record.msg == "request_failed" and getattr(record, "path", None) == "/users"]
    assert matching

    record = matching[-1]
    assert record.levelname == "WARNING"
    assert getattr(record, "status_code", None) == 400
    assert getattr(record, "error", None) == "Bad Request"
    details = getattr(record, "error_details", {})
    assert isinstance(details, dict)
    assert details.get("email") == "Required email string field"


def test_configure_logging_respects_log_level_and_json_output(monkeypatch, tmp_path):
    root_logger = logging.getLogger()
    previous_handlers = list(root_logger.handlers)
    previous_level = root_logger.level

    log_file_path = tmp_path / "app.log"

    try:
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        monkeypatch.setenv("LOG_FILE_PATH", str(log_file_path))

        app = Flask("observability-test")
        configure_logging(app)

        assert root_logger.level == logging.ERROR

        app.logger.error("forced_error_event", extra={"component": "tests", "alert_type": "manual"})
        for handler in root_logger.handlers:
            if hasattr(handler, "flush"):
                handler.flush()

        lines = log_file_path.read_text(encoding="utf-8").splitlines()
        assert lines

        payload = json.loads(lines[-1])
        assert payload["level"] == "ERROR"
        assert payload["message"] == "forced_error_event"
        assert payload["component"] == "tests"
        assert payload["alert_type"] == "manual"
    finally:
        current_handlers = list(root_logger.handlers)
        for handler in current_handlers:
            if handler not in previous_handlers:
                handler.close()

        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)
