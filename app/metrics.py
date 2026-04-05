import os
import time
from datetime import datetime, timedelta
from typing import Any

import psutil
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest


HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests handled by the application.",
    ["method", "path", "status"],
)

USERS_CREATED_TOTAL = Counter(
    "users_created_total",
    "Total number of users created.",
)

URLS_CREATED_TOTAL = Counter(
    "urls_created_total",
    "Total number of short URLs created.",
)

URL_RESOLUTIONS_TOTAL = Counter(
    "url_resolutions_total",
    "Total number of successful URL resolutions.",
    ["source", "cache"],
)

EVENTS_CREATED_TOTAL = Counter(
    "events_created_total",
    "Total number of events created.",
    ["event_type"],
)

USERS_TOTAL = Gauge("users_total", "Current total users in the database.")
URLS_TOTAL = Gauge("urls_total", "Current total URLs in the database.")
URLS_ACTIVE_TOTAL = Gauge("urls_active_total", "Current active URLs in the database.")
URLS_NEW_LAST_24H_TOTAL = Gauge("urls_new_last_24h_total", "URLs created in the last 24 hours.")
EVENTS_TOTAL = Gauge("events_total", "Current total events in the database.")
ACTIVITY_LAST_HOUR_TOTAL = Gauge("activity_last_hour_total", "Events created in the last hour.")
RESOLUTIONS_TOTAL = Gauge("resolutions_total", "Total click-resolution events stored in the database.")

APP_CPU_PERCENT = Gauge("app_cpu_percent", "Application process CPU usage percentage.")
APP_MEMORY_RSS_BYTES = Gauge("app_memory_rss_bytes", "Application process memory RSS in bytes.")


_PROCESS = psutil.Process(os.getpid())
_APP_STARTED_AT = time.time()


def observe_http_request(method: str, path: str, status_code: int) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=str(status_code)).inc()


def observe_user_created() -> None:
    USERS_CREATED_TOTAL.inc()


def observe_url_created() -> None:
    URLS_CREATED_TOTAL.inc()


def observe_url_resolution(source: str, cache: str) -> None:
    URL_RESOLUTIONS_TOTAL.labels(source=source, cache=cache).inc()


def observe_event_created(event_type: str) -> None:
    normalized = event_type.strip() if isinstance(event_type, str) else "unknown"
    EVENTS_CREATED_TOTAL.labels(event_type=normalized or "unknown").inc()


def _safe_count(query) -> int:
    try:
        return int(query.count())
    except Exception:
        return 0


def collect_business_snapshot() -> dict[str, Any]:
    from app.models.event import Event
    from app.models.url import Url
    from app.models.user import User

    now = datetime.now()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_1h = now - timedelta(hours=1)

    users_total = _safe_count(User.select())
    urls_total = _safe_count(Url.select())
    urls_active_total = _safe_count(Url.select().where(Url.is_active == True))
    urls_new_24h = _safe_count(Url.select().where(Url.created_at >= cutoff_24h))
    events_total = _safe_count(Event.select())
    activity_last_hour = _safe_count(Event.select().where(Event.timestamp >= cutoff_1h))
    resolutions_total = _safe_count(Event.select().where(Event.event_type == "click"))

    USERS_TOTAL.set(users_total)
    URLS_TOTAL.set(urls_total)
    URLS_ACTIVE_TOTAL.set(urls_active_total)
    URLS_NEW_LAST_24H_TOTAL.set(urls_new_24h)
    EVENTS_TOTAL.set(events_total)
    ACTIVITY_LAST_HOUR_TOTAL.set(activity_last_hour)
    RESOLUTIONS_TOTAL.set(resolutions_total)

    return {
        "users_total": users_total,
        "urls_total": urls_total,
        "urls_active_total": urls_active_total,
        "urls_new_last_24h_total": urls_new_24h,
        "events_total": events_total,
        "activity_last_hour_total": activity_last_hour,
        "resolutions_total": resolutions_total,
    }


def collect_runtime_snapshot() -> dict[str, Any]:
    cpu_percent = psutil.cpu_percent(interval=None)
    memory_info = _PROCESS.memory_info()
    uptime_seconds = round(time.time() - _APP_STARTED_AT, 2)

    APP_CPU_PERCENT.set(cpu_percent)
    APP_MEMORY_RSS_BYTES.set(memory_info.rss)

    virtual_mem = psutil.virtual_memory()

    return {
        "cpu_percent": cpu_percent,
        "memory": {
            "total_mb": round(virtual_mem.total / (1024 * 1024), 2),
            "available_mb": round(virtual_mem.available / (1024 * 1024), 2),
            "used_mb": round(virtual_mem.used / (1024 * 1024), 2),
            "percent": virtual_mem.percent,
        },
        "process": {
            "pid": _PROCESS.pid,
            "rss_mb": round(memory_info.rss / (1024 * 1024), 2),
            "threads": _PROCESS.num_threads(),
            "uptime_seconds": uptime_seconds,
        },
    }


def generate_prometheus_metrics() -> tuple[bytes, str]:
    collect_runtime_snapshot()
    try:
        collect_business_snapshot()
    except Exception:
        # Keep metrics endpoint scrapeable even if database queries fail.
        pass

    return generate_latest(), CONTENT_TYPE_LATEST
