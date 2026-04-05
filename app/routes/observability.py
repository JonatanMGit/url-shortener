import os
import time

import psutil
from flask import Blueprint, jsonify


observability_bp = Blueprint("observability", __name__)
_APP_STARTED_AT = time.time()
_PROCESS = psutil.Process(os.getpid())


@observability_bp.route("/metrics", methods=["GET"])
def metrics():
    virtual_mem = psutil.virtual_memory()
    process_mem = _PROCESS.memory_info()

    payload = {
        "kind": "metrics",
        "sample": {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory": {
                "total_mb": round(virtual_mem.total / (1024 * 1024), 2),
                "available_mb": round(virtual_mem.available / (1024 * 1024), 2),
                "used_mb": round(virtual_mem.used / (1024 * 1024), 2),
                "percent": virtual_mem.percent,
            },
            "process": {
                "pid": _PROCESS.pid,
                "rss_mb": round(process_mem.rss / (1024 * 1024), 2),
                "threads": _PROCESS.num_threads(),
                "uptime_seconds": round(time.time() - _APP_STARTED_AT, 2),
            },
        },
    }

    return jsonify(payload), 200
