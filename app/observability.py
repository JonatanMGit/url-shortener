import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

from flask import Request, g, request

from app.metrics import observe_http_request


_STANDARD_LOG_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_FIELDS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def _log_level_from_env() -> int:
    configured = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, configured, logging.INFO)


def configure_logging(app) -> None:
    level = _log_level_from_env()
    formatter = JsonLogFormatter()

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    log_file_path = os.environ.get("LOG_FILE_PATH", "").strip()
    if log_file_path:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    app.logger.handlers.clear()
    app.logger.propagate = True
    app.logger.setLevel(level)

    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.handlers.clear()
    werkzeug_logger.propagate = True
    werkzeug_logger.setLevel(level)

    app.logger.info(
        "logging_configured",
        extra={
            "component": "observability",
            "log_level": logging.getLevelName(level),
            "log_file_path": log_file_path or None,
        },
    )


def _request_path(current_request: Request) -> str:
    return current_request.path or "/"


def register_request_logging(app) -> None:
    @app.before_request
    def _before_request() -> None:
        g.request_started_at = time.perf_counter()

    @app.after_request
    def _after_request(response):
        started_at = getattr(g, "request_started_at", None)
        duration_ms = None
        if isinstance(started_at, float):
            duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)

        log_extra: dict[str, Any] = {
            "component": "http",
            "method": request.method,
            "path": _request_path(request),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "remote_addr": request.remote_addr,
        }

        route_pattern = request.url_rule.rule if request.url_rule and request.url_rule.rule else _request_path(request)
        observe_http_request(request.method, route_pattern, response.status_code)

        if response.status_code >= 400 and response.is_json:
            payload = response.get_json(silent=True)
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, str):
                    log_extra["error"] = error

                details = payload.get("details")
                if isinstance(details, (dict, str)):
                    log_extra["error_details"] = details

        if response.status_code >= 500:
            app.logger.error("request_failed", extra=log_extra)
        elif response.status_code >= 400:
            app.logger.warning("request_failed", extra=log_extra)
        else:
            app.logger.info("request_complete", extra=log_extra)

        return response
