import json
from typing import Any
from flask import Blueprint, current_app, redirect, jsonify
from peewee import DoesNotExist

from app.cache import build_resolve_cache_key
from app.models.url import Url
from app.models.event import Event

resolve_bp = Blueprint("resolve", __name__, url_prefix="/r")

@resolve_bp.route("/<string:short_code>", methods=["GET"])
def resolve_url(short_code: str) -> Any:
    cache = current_app.extensions.get("cache")
    cache_key = build_resolve_cache_key(short_code)

    cached_payload = cache.get_json(cache_key) if cache else None
    if cached_payload:
        if not cached_payload.get("is_active", True):
            response = jsonify({"error": "Gone", "details": "This URL is no longer active"})
            response.status_code = 410
            response.headers["X-Cache"] = "HIT"
            return response

        Event.create(
            url_id=cached_payload.get("url_id"),
            user_id=cached_payload.get("user_id"),
            event_type="click",
            details=json.dumps({"short_code": short_code, "action": "redirect"})
        )

        response = redirect(cached_payload.get("original_url"), code=302)
        response.headers["X-Cache"] = "HIT"
        return response

    try:
        url = Url.get(Url.short_code == short_code)
    except DoesNotExist:
        return jsonify({"error": "Not Found", "details": "Short code does not exist"}), 404
        
    if not url.is_active:
        return jsonify({"error": "Gone", "details": "This URL is no longer active"}), 410
        
    # Log the click event based on the new platform architecture
    Event.create(
        url_id=url,
        user_id=url.user_id,
        event_type="click",
        details=json.dumps({"short_code": short_code, "action": "redirect"})
    )

    if cache:
        cache.set_json(cache_key, {
            "url_id": url.id,
            "user_id": url.user_id.id,
            "original_url": url.original_url,
            "is_active": url.is_active,
        })

    response = redirect(url.original_url, code=302)
    response.headers["X-Cache"] = "MISS"
    return response
