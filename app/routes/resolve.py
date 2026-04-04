import json
from typing import Any
from flask import Blueprint, redirect, jsonify
from peewee import DoesNotExist

from app.models.url import Url
from app.models.event import Event

resolve_bp = Blueprint("resolve", __name__, url_prefix="/r")

@resolve_bp.route("/<string:short_code>", methods=["GET"])
def resolve_url(short_code: str) -> Any:
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
    
    return redirect(url.original_url, code=302)
