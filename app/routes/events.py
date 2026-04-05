import json
from flask import Blueprint, jsonify, request
from playhouse.shortcuts import model_to_dict
from peewee import DataError

from app.metrics import observe_event_created
from app.models.event import Event
from app.models.url import Url
from app.models.user import User

events_bp = Blueprint("events", __name__, url_prefix="/events")

@events_bp.route("", methods=["GET"])
def list_events():
    raw_url_id = request.args.get("url_id")
    raw_user_id = request.args.get("user_id")
    url_id = request.args.get("url_id", type=int)
    user_id = request.args.get("user_id", type=int)
    event_type = request.args.get("event_type")

    if raw_url_id is not None and url_id is None:
        return jsonify({"error": "Bad Request", "details": {"url_id": "Must be an integer"}}), 400
    if raw_user_id is not None and user_id is None:
        return jsonify({"error": "Bad Request", "details": {"user_id": "Must be an integer"}}), 400
    
    query = Event.select()
    if url_id is not None:
        query = query.where(Event.url_id == url_id)
    if user_id is not None:
        query = query.where(Event.user_id == user_id)
    if event_type is not None:
        query = query.where(Event.event_type == event_type)
        
    events = query
    result = []
    
    for event in events:
        event_dict = model_to_dict(event, recurse=False)
        
        # Parse details string back to JSON
        if event.details:
            try:
                event_dict["details"] = json.loads(event.details)
            except json.JSONDecodeError:
                pass
                
        result.append(event_dict)
        
    return jsonify({"kind": "list", "sample": result, "total_items": len(result)}), 200

@events_bp.route("", methods=["POST"])
def create_event():
    data = request.get_json()
    if not isinstance(data, dict) or "event_type" not in data:
        return jsonify({"error": "Bad Request", "details": {"event_type": "Required"}}), 400

    event_type = data.get("event_type")
    if not isinstance(event_type, str) or not event_type.strip():
        return jsonify({"error": "Bad Request", "details": {"event_type": "Required non-empty string"}}), 400

    if "url_id" not in data or "user_id" not in data:
        return jsonify({"error": "Bad Request", "details": {"identity": "url_id and user_id are required"}}), 400

    url_id_val = data.get("url_id")
    user_id_val = data.get("user_id")

    if url_id_val is not None and not isinstance(url_id_val, int):
        return jsonify({"error": "Bad Request", "details": {"url_id": "Must be an integer"}}), 400
    if user_id_val is not None and not isinstance(user_id_val, int):
        return jsonify({"error": "Bad Request", "details": {"user_id": "Must be an integer"}}), 400

    details_obj = data.get("details", {})
    if details_obj is None:
        details_obj = {}
    if not isinstance(details_obj, dict):
        return jsonify({"error": "Bad Request", "details": {"details": "Must be an object"}}), 400

    try:
        url = Url.get_by_id(url_id_val) if url_id_val is not None else None
        user = User.get_by_id(user_id_val) if user_id_val is not None else None
    except DataError:
        return jsonify({"error": "Bad Request", "details": {"identity": "Invalid ID format"}}), 400

    if url is not None and user is not None and url.user_id.id != user.id:
        return jsonify({"error": "Unprocessable Entity", "details": {"identity": "url_id does not belong to user_id"}}), 422

    details_val = json.dumps(details_obj)
        
    event = Event.create(
        url_id=url,
        user_id=user,
        event_type=event_type.strip(),
        details=details_val
    )
    observe_event_created(event_type.strip())
    
    event_dict = model_to_dict(event, recurse=False)
    event_dict["details"] = json.loads(event.details) if event.details else {}
    return jsonify(event_dict), 201