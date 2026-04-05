from flask import Blueprint, Response, jsonify

from app.metrics import collect_business_snapshot, collect_runtime_snapshot, generate_prometheus_metrics


observability_bp = Blueprint("observability", __name__)


@observability_bp.route("/metrics", methods=["GET"])
def metrics():
    runtime_sample = collect_runtime_snapshot()
    business_sample = collect_business_snapshot()

    payload = {
        "kind": "metrics",
        "sample": {
            **runtime_sample,
            "business": business_sample,
        },
    }

    return jsonify(payload), 200


@observability_bp.route("/metrics/prometheus", methods=["GET"])
def prometheus_metrics() -> Response:
    payload, content_type = generate_prometheus_metrics()
    return Response(payload, mimetype=content_type)
